# train_logo.py
from ultralytics import YOLO

def main():
    # choose pretrained backbone; change to yolov8s.pt for better accuracy
    model = YOLO("yolov8s.pt")

    # trains and writes runs/detect/train/weights/best.pt
    model.train(
        data="logo_dataset.yaml",
        epochs=40,
        imgsz=640,
        batch=8
    )

if __name__ == "__main__":
    main()