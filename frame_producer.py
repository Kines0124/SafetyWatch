import cv2
import requests
import time
import os
import uuid

VIDEO_PATH = "data/Video-Teste.mp4"
DETECTEPI_URL = "http://localhost:8000/predict/image"
N8N_WEBHOOK_URL = "http://localhost:5678/webhook/deteccao-epi"
FRAME_SKIP = 5
TEMP_FRAME_PATH = "temp_frame.jpg"

VIOLATION_CLASSES = {"NO-Safety Helmet", "NO-Safety Vest"}
GAP_TOLERANCE = 8.0       # segundos sem detecção até considerar o incidente encerrado
HEARTBEAT_INTERVAL = 600.0  # 10 minutos, em segundos


def open_incident(timestamp):
    return {
        "incident_id": str(uuid.uuid4()),
        "start_time": timestamp,
        "last_seen_time": timestamp,
        "last_heartbeat_time": timestamp,
        "classes": {}
    }


def update_classes(incident, class_counts, class_max_conf, timestamp):
    for cls, count in class_counts.items():
        if cls not in incident["classes"]:
            incident["classes"][cls] = {
                "first_seen": timestamp,
                "last_seen": timestamp,
                "max_confidence": class_max_conf[cls],
                "max_concurrent": count
            }
        else:
            entry = incident["classes"][cls]
            entry["last_seen"] = timestamp
            entry["max_confidence"] = max(entry["max_confidence"], class_max_conf[cls])
            entry["max_concurrent"] = max(entry["max_concurrent"], count)


def build_payload(incident, status, current_time):
    classes_dict = {
        cls: {
            "max_confidence": round(info["max_confidence"], 4),
            "max_concurrent": info["max_concurrent"]
        }
        for cls, info in incident["classes"].items()
    }
    return {
        "incident_id": incident["incident_id"],
        "status": status,
        "start_time": round(incident["start_time"], 2),
        "end_time": round(current_time, 2),
        "duration": round(current_time - incident["start_time"], 2),
        "classes": classes_dict
    }

def send_event(incident, status, current_time):
    payload = build_payload(incident, status, current_time)
    try:
        requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5)
        classes_str = [c["class"] for c in payload["classes"]]
        print(f"[{status.upper()}] {incident['incident_id'][:8]} | {payload['duration']}s | {classes_str}")
    except requests.RequestException as e:
        print(f"Erro ao enviar evento pro n8n: {e}")


def main():
    cap = cv2.VideoCapture(VIDEO_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_number = 0
    incident = None

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
                detections = response.json().get("detections", [])
                violations = [d for d in detections if d["class"] in VIOLATION_CLASSES]

                if violations:
                    class_counts, class_max_conf = {}, {}
                    for d in violations:
                        c = d["class"]
                        class_counts[c] = class_counts.get(c, 0) + 1
                        class_max_conf[c] = max(class_max_conf.get(c, 0), d["confidence"])

                    if incident is None:
                        incident = open_incident(timestamp)
                        update_classes(incident, class_counts, class_max_conf, timestamp)
                        send_event(incident, "new", timestamp)
                    else:
                        incident["last_seen_time"] = timestamp
                        update_classes(incident, class_counts, class_max_conf, timestamp)

                    if incident and (timestamp - incident["last_heartbeat_time"]) >= HEARTBEAT_INTERVAL:
                        incident["last_heartbeat_time"] = timestamp
                        send_event(incident, "ongoing", timestamp)
                else:
                    if incident is not None:
                        gap = timestamp - incident["last_seen_time"]
                        if gap >= GAP_TOLERANCE:
                            send_event(incident, "closed", incident["last_seen_time"])
                            incident = None
            else:
                print(f"Erro no DetectEPI ({response.status_code}) no frame {frame_number}")

        frame_number += 1
        time.sleep(1 / fps)

    if incident is not None:
        send_event(incident, "closed", incident["last_seen_time"])

    cap.release()
    if os.path.exists(TEMP_FRAME_PATH):
        os.remove(TEMP_FRAME_PATH)
    print("Processamento concluído.")


if __name__ == "__main__":
    main()