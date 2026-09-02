import cv2
import requests
import time
import os

VIDEO_PATH = "data/Video-Teste.mp4"
DETECTEPI_URL = "http://localhost:8000/predict/image"
N8N_WEBHOOK_URL = "http://localhost:5678/webhook/deteccao-epi"
FRAME_SKIP = 5
TEMP_FRAME_PATH = "temp_frame.jpg"

VIOLATION_CLASSES = {"NO-Safety Helmet", "NO-Safety Vest"}

def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_number = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_number % FRAME_SKIP == 0:
            timestamp = frame_number / fps
            cv2.imwrite(TEMP_FRAME_PATH, frame)

            with open(TEMP_FRAME_PATH, "rb") as f:
                files = {"file": (TEMP_FRAME_PATH, f, "image/jpeg")}
                response = requests.post(DETECTEPI_URL, files=files)

            if response.status_code == 200:
                data = response.json()
                detections = data.get("detections", [])
                violations = [d for d in detections if d["class"] in VIOLATION_CLASSES]

                if violations:
                    payload = {
                        "frame_number": frame_number,
                        "timestamp": round(timestamp, 2),
                        "detections": violations
                    }
                    requests.post(N8N_WEBHOOK_URL, json=payload)
                    print(f"Frame {frame_number}: {len(violations)} violação(ões) enviada(s)")
            else:
                print(f"Erro no DetectEPI ({response.status_code}) no frame {frame_number}")

        frame_number += 1
        time.sleep(1 / fps)

    cap.release()
    if os.path.exists(TEMP_FRAME_PATH):
        os.remove(TEMP_FRAME_PATH)
    print("Processamento concluído.")

if __name__ == "__main__":
    main()