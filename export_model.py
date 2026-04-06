# export_model.py
import shutil
import os

def export_best(run_dir="runs/detect/train13", dest="models/best_t13.pt"):
    src = os.path.join(run_dir, "weights", "best.pt")
    if not os.path.exists(src):
        raise FileNotFoundError(src)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(src, dest)
    print("Copied", src, "->", dest)

if __name__ == "__main__":
    export_best()