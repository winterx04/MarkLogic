from ultralytics import YOLO
import torch

def main():
    # 1. Hardware Verification
    if torch.cuda.is_available():
        print(f"✅ GPU found: {torch.cuda.get_device_name(0)}")
        torch.cuda.empty_cache()
        device = 0
    else:
        print("❌ GPU not found by PyTorch. Falling back to CPU.")
        device = "cpu"

    # 2. Load base model — FINE-TUNING from best_colab3 (not a fresh start).
    # best_colab3 already knows how to find/classify fields on these documents;
    # warm-starting from it reuses that instead of relearning it from scratch.
    # If final_dataset/logo_dataset.yaml has been updated to nc:10 (text_logo
    # added), Ultralytics reinitializes just the final classification layer to
    # match — the rest of the backbone's learned weights carry over as-is.
    
    # model = YOLO("models/best_colab3.pt")
    model = YOLO("models/best_text_logo_v2.pt")  
    # 3. Training
    model.train(
        name="train-logo-merged",   # text_logo merged into logo (final_dataset_merged); own folder so it never mixes with older runs
        exist_ok=False,     # auto-increments to train-text-logo2, train-text-logo3, ...
                            # instead of overwriting the same run every time (exist_ok=True
                            # was silently clobbering the previous run's results/weights).
        data=r"C:\Users\xian.xin\MarkLogic\final_dataset_merged\logo_dataset.yaml",   # built by make_merged_dataset.py (text_logo -> logo)

        epochs=100,         # Larger dataset now (1,123 images) than the original
                            # 48-image run this script was tuned for — needs fewer
                            # epochs to converge; patience will stop it earlier anyway.

        imgsz=640,
        batch=16,           # RTX 5070 8GB (vs. the 4GB card this was tuned for before) —
                            # doubled from 8. Drop to 8 if you hit a CUDA OOM error.

        device=device,

        # RTX 5070 Laptop (8GB VRAM) + 32 logical CPU cores:
        workers=8,          # More than 4 now that there are real cores to spare,
                            # but not maxed to 32 — diminishing returns past ~8 for
                            # a dataset this size, and it's not worth the overhead.
        amp=True,
        cache=True,         # Fine to cache in RAM at this dataset size (1,123 images)

        # FINE-TUNING TUNING (different from a fresh-start run):
        patience=20,
        val=True,
        lr0=0.0002,          # Lower than the fresh-start default (0.01) — warm-starting
                            # from a checkpoint that already works needs gentler updates,
                            # not large steps that could undo what it already learned.
        lrf=0.1,            # Lower than the fresh-start default (0.2) — same reasoning as lr0.
        warmup_epochs=2,    # Less warmup needed than a fresh start from ImageNet weights
        optimizer="AdamW",  # AdamW is better for fine-tuning than SGD (default for fresh-start runs)

        # DATA AUGMENTATION:
        #augment=True, # (it's for prediction-time augmentation).
        flipud=0.0,         #Default 0.1
        fliplr=0.0,         #Default 0.5
        mosaic=0.5,  #Default 1.0       #Mosaic stitches four pages into one. That breaks the layout cues (a logo at the top, text below), and for a layout-reading model those cues are how it tells the classes apart.
        degrees=5.0,
        scale=0.3,
    )

if __name__ == "__main__":
    main()
