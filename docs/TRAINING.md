# Real data, training, and artifact uploads

No checkpoint, labeled dataset, or reported accuracy is invented. The supplied paper describes the components and selected hyperparameters but does not supply a reproducible dataset or original source. This code is a documented implementation of those ideas, not a claim of identical weights, parameter count, latency, or accuracy.

## Data requirements

Obtain aligned, licensed Sentinel-2 RGB/NIR and Sentinel-1 RTC VV/VH acquisitions and complete human-reviewed binary change labels. Assign geographic sites to **disjoint** train, validation, and test groups. Keep neighboring/overlapping tiles and the same geographic site in one split. The audit checks actual WGS84 polygons for overlap and a minimum 1 km separation between splits, plus group IDs, paths, content hashes, tensor values, source IDs, provenance, complete label coverage, and review metadata. This contract cannot certify that human annotations are correct or that evaluation generalizes.

Labels describe changed/disturbed ground, not a proven legal violation. Unannotated regions can be used as negative labels only if they have been exhaustively reviewed. Do not train by labeling every pixel outside known concessions as illegal.

Install ML dependencies on your training machine:

```bash
cd backend
pip install -r requirements-ml.txt
```

## Prepare from actual STAC acquisitions

Create your own `samples.json`, a list of records with these fields:

| Field | Required value |
| --- | --- |
| `group` | Geographic site identifier |
| `split` | `train`, `validation`, or `test` |
| `geometry` | WGS84 study Polygon/MultiPolygon |
| `optical_before`, `optical_after` | Real `sentinel-2-l2a` STAC item IDs |
| `radar_before`, `radar_after` | Real `sentinel-1-rtc` STAC item IDs on the same relative orbit/direction |
| `labels` | Actual manually reviewed GeoJSON FeatureCollection of positive change polygons |
| `annotation` | `status: reviewed`, `coverage: complete`, reviewer identity and timezone-qualified `reviewed_at` |

The files must contain actual acquisitions and annotations; no example satellite records are bundled.

```bash
python -m app.ml.prepare --samples /path/to/real/samples.json \
  --provenance /path/to/real/provenance.json --output /path/to/new/dataset
```

Preparation fetches the actual source records, checks full spatial coverage and matching radar orbits, reads/radiometrically normalizes/co-registers source COGs, rasterizes labels, and emits 512×512 tiles at 10m. Supply temporally matched acquisitions; source dates should differ by no more than 12 days within each epoch, consistent with the application. The preparation tool does not automatically discover labels or establish ground truth.

Each `.npz` has:

- `before`, `after`: float32 `6×512×512`, channel order **red, green, blue, NIR, VV, VH**.
- Optical channels: surface reflectance, clipped to `[0,1]`.
- SAR channels: gamma0 linear intensity normalized as `(10*log10(max(x,1e-8))+25)/25`.
- `mask`: binary `1×512×512` change labels.
- `valid`: binary `1×512×512`; zero for padding/invalid radar/unknown labels.
- `cloud`: binary `2×512×512`; one for invalid/cloudy optical pixels at each epoch.

`manifest.json` contains `train`, `validation`, and `test` lists. Each record includes `path`, `group`, actual geometry, source scene IDs, reviewer metadata, and a SHA-256 hash. Top-level `provenance` requires dataset_name, HTTPS source_url, license, annotation_protocol, label_type `disturbance_change`, and resolution_m `10`. All split lists must be nonempty. No path may escape the dataset directory.

## Upload/import an existing real dataset

Transfer the labeled dataset ZIP to your training host or mounted workspace through your preferred secure file transfer. The operator import command accepts a ZIP with `manifest.json` at its root and `.npz` tiles. It rejects traversal paths, symlinks, unsupported file types, and oversized archives, and validates tensor shapes/content.

```bash
python -m app.ml.artifacts import-dataset \
  --archive /uploads/real-labeled-dataset.zip \
  --destination /data/datasets/version-1
```

This is an operator workflow, not an anonymous browser upload or public GPU-execution endpoint. Concession boundaries have a separate authenticated browser import in the application.

## Train and evaluate

```bash
python -m app.ml.train \
  --dataset /data/datasets/version-1 \
  --output /data/checkpoints/version-1 \
  --epochs 50 --batch-size 1 --accumulate 4 --amp --device cuda
```

The paper gives batch size 16 on a 24GB RTX 4090. This implementation defaults to 4 because its architecture differs and memory requirements need measurement. Tune only on validation data. Use geographically held-out tests for the final report.

The trainer uses AdamW, learning rate `1e-4`, weight decay `1e-2`, cosine scheduling, and weighted BCE/focal/boundary loss (`0.4/0.4/0.2`). It saves the best validation-F1 checkpoint and history after each epoch. Test evaluation is disabled by default; use `--evaluate-test` only for a frozen, final experiment selected without consulting test results. `--warm-start` loads trusted safetensors weights into a new run with a fresh optimizer/schedule; it is not an exact training resume. Training history and measured precision/recall/F1/foreground IoU are saved. Foreground IoU is labeled accurately; the paper's displayed formula is not a class-averaged mIoU.

Output files:

- `model.safetensors`: tensor-only weights; no arbitrary pickle loading.
- `manifest.json`: architecture, checkpoint SHA-256, normalization, source-manifest hash, threshold, measured validation/test metrics, training epoch, and timestamp.
- `history.json`: observed training history.

The implementation currently uses two Swin-Tiny encoders shared across time, and approximately **58.6M parameters**. It implements local cross attention for bounded memory, an explicit cloud gate, a physical PATM filter, and a multi-scale difference decoder. These are concrete implementation decisions where the paper lacks code-level detail. Evaluate them with ablations on your own data before drawing research conclusions.

## Install/upload the trained model

Before installation, review real validation and held-out test metrics against criteria set before inspecting the test result. The trainer marks artifacts `release_approved: false`; inference stays disabled until an operator approves a checksum-verified artifact with reviewer identity, region, written notes and explicit minimum F1/precision.

```bash
python -m app.ml.artifacts approve-model --source /data/checkpoints/version-1 \
  --reviewer YOUR_REVIEWER --region YOUR_EVALUATED_REGION --notes /path/to/release-review.md \
  --minimum-f1 YOUR_PREDECLARED_THRESHOLD --minimum-precision YOUR_PREDECLARED_THRESHOLD
```

Transfer the real checkpoint directory to the worker volume, then validate and install into a **new immutable version directory**:

```bash
python -m app.ml.artifacts install-model \
  --source /uploads/checkpoint-version-1 \
  --destination /data/models/version-1
```

Configure:

```text
MODEL_PATH=/data/models/version-1/model.safetensors
MODEL_MANIFEST_PATH=/data/models/version-1/manifest.json
```

Ensure ML dependencies are installed on the inference worker. The API must have access to matching artifact paths for readiness/engine selection, or deploy a shared matching artifact image. Restart both services after selecting an artifact version. The worker checks architecture/weights compatibility and SHA-256 before inference. Never install unreviewed public weights or substitute random initialized weights for a checkpoint.

## What this does not establish

Model confidence calibration, illegal mining ground truth, generalization to other countries/seasons, commercial imagery support, the paper's quoted 93.8% F1, or 29.4ms latency. Those require real evaluation; no application UI displays them as achieved results.

## Public Africa physical analysis and neural training

The application’s keyless physical detector now uses Digital Earth Africa RTC on a 30m analysis grid. This preparation/training pipeline intentionally retains the documented 10m Planetary Computer input contract. It does not silently upscale the public radar and call it equivalent neural training data. To train/infer the current neural architecture, provide compatible 10m RTC access and real labels, or explicitly develop and evaluate a separately versioned 30m model.

## Free Colab workflow

Open `backend/notebooks/GeoMine_Real_Data_Training.ipynb` in Colab and select a free GPU runtime. Upload the reviewed source ZIP, mount Drive to persist output, and import your actual audited dataset ZIP. The notebook checks CUDA and the dataset before allocating the model, uses AMP and gradient accumulation, plots observed history, and separates optional final-test evaluation from release review. Colab may not grant a free GPU and may interrupt sessions; no paid compute is enabled automatically. No training has been performed or weights supplied by this project delivery.

## Real source material for annotation planning

The CC-BY-SA 4.0 global mining metadata at https://zenodo.org/records/14195737 was downloaded and MD5-verified. It contains static mining extents and source metadata, not bitemporal SAR/optical disturbance labels. The curation-sites JSON delivered alongside the notebook contains actual Ghana candidate sites for human annotation planning; all remain unreviewed for temporal change and must not be used as training truth.

EuroMineNet (https://rodare.hzdr.de/record/4656, CC-BY 4.0) supplies multiyear optical data, not the complete aligned SAR/optical contract. Neither dataset substitutes for the paper's unreleased paired labels. Respect source licenses and attribution, and verify any redistribution obligations. The current 10 m preparation workflow still needs compatible source access; the keyless 30 m radar workflow cannot silently substitute for it.
