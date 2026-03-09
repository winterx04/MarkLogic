from ultralytics import YOLO
import torch

def main():
    # 1. Hardware Verification
    if torch.cuda.is_available():
        print(f"✅ GPU found: {torch.cuda.get_device_name(0)}")
        # Clear cache before starting to free up any fragmented VRAM
        torch.cuda.empty_cache()
        device = 0
    else:
        print("❌ GPU not found by PyTorch. Falling back to CPU.")
        device = "cpu"

    # 2. Load the model
    # yolov8s is a good balance for a 3050. 
    # If you still get memory errors, switch this to "yolov8n.pt" (Nano)
    model = YOLO("yolov8s.pt")

    # 3. Tuned Training Parameters
    model.train(
        data="logo_dataset.yaml",
        epochs=40,
        imgsz=640,          # Standard size. Do not go higher on 4GB VRAM.
        batch=8,            # TUNED: 16 is likely too high for 4GB. 8 is the "Sweet Spot".
        device=device,
        
        # PC SPECIFIC TUNING:
        workers=4,          # Ryzen 5 5600H has 6 cores. 4 workers is efficient without lag.
        amp=True,           # Automatic Mixed Precision: Uses half-memory for math (Saves VRAM).
        cache=True,         # You have 16GB RAM; caching images in system RAM speeds up training.
        
        # ACCURACY TUNING:
        patience=10,        # Early stopping: stops if no improvement for 10 epochs.
        overlap_mask=True,  # Better for overlapping logos.
        val=True            # Run validation after each epoch to monitor progress.
    )

if __name__ == "__main__":
    main()