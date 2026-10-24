"""Paper-informed implementation; not the authors' unavailable original weights/code."""

import timm
import torch
from torch import nn
from torch.nn import functional as F


class CrossAttentionFusion(nn.Module):
    def __init__(self, channels, heads=4, window=8):
        super().__init__()
        self.window = window
        self.query_norm = nn.LayerNorm(channels)
        self.radar_norm = nn.LayerNorm(channels)
        self.attention = nn.MultiheadAttention(
            channels, heads, batch_first=True, dropout=0.1
        )
        self.output_norm = nn.LayerNorm(channels)

    def forward(self, optical, radar, cloud):
        # timm Swin features use NHWC. Windowed cross attention bounds memory.
        b, h, w, c = optical.shape
        size = self.window
        ph, pw = (size - h % size) % size, (size - w % size) % size

        def windows(x):
            x = F.pad(x.permute(0, 3, 1, 2), (0, pw, 0, ph)).permute(0, 2, 3, 1)
            return (
                x.reshape(b, (h + ph) // size, size, (w + pw) // size, size, c)
                .permute(0, 1, 3, 2, 4, 5)
                .reshape(-1, size * size, c)
            )

        q, k = windows(optical), windows(radar)
        fused, _ = self.attention(
            self.query_norm(q),
            self.radar_norm(k),
            self.radar_norm(k),
            need_weights=False,
        )
        fused = (
            self.output_norm(fused + q)
            .reshape(b, (h + ph) // size, (w + pw) // size, size, size, c)
            .permute(0, 1, 3, 2, 4, 5)
            .reshape(b, h + ph, w + pw, c)[:, :h, :w]
        )
        cloud = F.interpolate(cloud, size=(h, w), mode="nearest").permute(0, 2, 3, 1)
        # Cloudy optical locations use radar directly. Both pathways are trained.
        return fused * (1 - cloud) + radar * cloud


class GeoMineXNet(nn.Module):
    architecture = "geomine-xnet-swin-tiny-v1"

    def __init__(self, image_size=512):
        super().__init__()
        self.image_size = image_size
        self.optical = timm.create_model(
            "swin_tiny_patch4_window7_224",
            pretrained=False,
            features_only=True,
            img_size=image_size,
            window_size=8,
            in_chans=4,
        )
        self.radar = timm.create_model(
            "swin_tiny_patch4_window7_224",
            pretrained=False,
            features_only=True,
            img_size=image_size,
            window_size=8,
            in_chans=2,
        )
        channels = self.optical.feature_info.channels()
        self.fusions = nn.ModuleList([CrossAttentionFusion(c) for c in channels])
        self.projections = nn.ModuleList([nn.Conv2d(c, 64, 1) for c in channels])
        self.decoder = nn.Sequential(
            nn.Conv2d(256, 128, 3, padding=1),
            nn.GroupNorm(8, 128),
            nn.GELU(),
            nn.Conv2d(128, 64, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(64, 1, 1),
        )

    def forward(self, before, after, cloud=None, legal=None):
        if before.shape != after.shape or before.shape[1] != 6:
            raise ValueError("Expected aligned B×6×H×W RGB,NIR,VV,VH tensors.")
        b, _, h, w = before.shape
        if (h, w) != (self.image_size, self.image_size):
            raise ValueError(f"Expected {self.image_size}×{self.image_size} tiles.")
        if cloud is None:
            cloud = before.new_zeros((b, 2, h, w))
        opt1, opt2 = self.optical(before[:, :4]), self.optical(after[:, :4])
        sar1, sar2 = self.radar(before[:, 4:]), self.radar(after[:, 4:])
        differences = []
        for i, (fuse, project) in enumerate(zip(self.fusions, self.projections)):
            one = fuse(opt1[i], sar1[i], cloud[:, 0:1])
            two = fuse(opt2[i], sar2[i], cloud[:, 1:2])
            delta = project(torch.abs(two - one).permute(0, 3, 1, 2))
            differences.append(
                F.interpolate(
                    delta, size=(h // 4, w // 4), mode="bilinear", align_corners=False
                )
            )
        raw = F.interpolate(
            self.decoder(torch.cat(differences, dim=1)),
            size=(h, w),
            mode="bilinear",
            align_corners=False,
        )
        # PATM: stable radar plus optical vegetation change suggests seasonal variation.
        n1 = (before[:, 3:4] - before[:, 0:1]) / (
            before[:, 3:4] + before[:, 0:1] + 1e-6
        )
        n2 = (after[:, 3:4] - after[:, 0:1]) / (after[:, 3:4] + after[:, 0:1] + 1e-6)
        db_delta = torch.abs(after[:, 4:5] - before[:, 4:5]) * 25
        seasonal = (
            ((n1 - n2).abs() > 0.2)
            & (db_delta < 1)
            & (cloud.amax(dim=1, keepdim=True) < 0.5)
        )
        raw = raw - seasonal.to(raw.dtype) * 2
        probability = raw.sigmoid()
        return {
            "raw_logits": raw,
            "probability": probability,
            "outside_concessions": probability
            if legal is None
            else probability * (1 - legal),
            "seasonal_mask": seasonal,
        }
