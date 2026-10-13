import cv2


def draw_overlay(frame, boxes, alert, avg_count, density, occupancy=None):
    box_color = (0, 0, 255) if alert else (0, 200, 0)
    for (x1, y1, x2, y2) in boxes:
        cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)

    status = "OVERCROWDED" if alert else "NORMAL"
    cv2.putText(frame, f"People: {len(boxes)}  Avg: {avg_count:.1f}  Status: {status}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, box_color, 2)
    cv2.putText(frame, f"Density: {density:.1f} people/MP",
                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    if occupancy is not None:
        cv2.putText(frame, f"Occupancy: {occupancy:.1f}%",
                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return frame