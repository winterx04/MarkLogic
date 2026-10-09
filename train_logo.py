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
    model = YOLO("models/best_text_logo_v1.pt")  
    # 3. Training
    model.train(
        name="train-text-logo",
        exist_ok=False,     # auto-increments to train-text-logo2, train-text-logo3, ...
                            # instead of overwriting the same run every time (exist_ok=True
                            # was silently clobbering the previous run's results/weights).
        data=r"C:\\Users\\xian.xin\\MarkLogic\\final_dataset\\logo_dataset.yaml",

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
        lr0=0.001,          # Lower than the fresh-start default (0.01) — warm-starting
                            # from a checkpoint that already works needs gentler updates,
                            # not large steps that could undo what it already learned.
        warmup_epochs=2,    # Less warmup needed than a fresh start from ImageNet weights
        optimizer="auto",

        # DATA AUGMENTATION:
        augment=True,
        flipud=0.1,
        fliplr=0.5,
        mosaic=1.0,
        degrees=5.0,
        scale=0.3,
    )

if __name__ == "__main__":
    main()
