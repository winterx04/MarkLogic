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

    # 2. Load base model (fresh start — new 9-class dataset is different from old logo-only model)
    # yolov8s = small, good balance for 4GB VRAM + 9 classes
    # Switch to yolov8n.pt if you get CUDA out of memory errors
    model = YOLO("yolov8s.pt")

    # 3. Training
    model.train(
        data=r"C:\\Users\\xxin5\\MarkLogic\\final_dataset\\logo_dataset.yaml",

        epochs=150,         # More epochs since dataset is small (48 images)
                            # Early stopping will kick in before 100 if model converges

        imgsz=640,          # Standard size, fine for 4GB VRAM
        batch=8,            # Sweet spot for 4GB VRAM with 9 classes

        device=device,

        # PC SPECIFIC TUNING (Ryzen 5 5600H + 16GB RAM):
        workers=4,
        amp=True,           # Saves VRAM with mixed precision
        cache=True,         # Cache images in RAM for faster training

        # ACCURACY TUNING:
        patience=30,        # Increased from 10 — gives model more time to improve on small dataset
        val=True,
        lr0=0.01,           # Reset to default — starting fresh so no need for low LR
        warmup_epochs=5,    # Gentle warmup since dataset is small

        # DATA AUGMENTATION (critical for small datasets):
        augment=True,
        flipud=0.1,
        fliplr=0.5,
        mosaic=1.0,         # Combine 4 images — helps with small dataset
        degrees=5.0,        # Small rotation — logos can be slightly tilted
        scale=0.3,          # Random scale
    )

if __name__ == "__main__":
    main()