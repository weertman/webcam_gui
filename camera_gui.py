import sys
import os
import time
import cv2
import multiprocessing
import queue
import numpy as np
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QSpinBox, QCheckBox,
    QFormLayout, QMessageBox, QSizePolicy, QTabWidget
)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QTimer, Qt


class CameraProcess(multiprocessing.Process):
    """
    Each camera runs in its own process.
    - camera_index: the integer index of the camera (0, 1, 2, etc.)
    - settings: dict with 'fps', 'width', 'height', 'output_dir', 'chunk_minutes'
    - frame_queue: a multiprocessing.Queue to send compressed frames for preview
    """
    def __init__(self, camera_index, settings, frame_queue):
        super().__init__()
        self.camera_index = camera_index
        self.settings = settings
        self.frame_queue = frame_queue
        self.stop_event = multiprocessing.Event()

        self.cap = None
        self.out = None

        # For splitting videos:
        self.segment_start_time = None
        self.segment_index = 0

    def run(self):
        # Open the camera
        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            print(f"[Camera {self.camera_index}] Cannot open camera.")
            return

        # Apply user settings (0 => default)
        if self.settings["width"] > 0:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings["width"])
        if self.settings["height"] > 0:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings["height"])
        if self.settings["fps"] > 0:
            self.cap.set(cv2.CAP_PROP_FPS, self.settings["fps"])

        time.sleep(1)  # Let camera adjust

        # Ensure output directory
        if not os.path.exists(self.settings["output_dir"]):
            os.makedirs(self.settings["output_dir"], exist_ok=True)

        # Start first video segment
        self.start_new_segment()

        # Main loop
        while not self.stop_event.is_set():
            ret, frame = self.cap.read()
            if not ret:
                print(f"[Camera {self.camera_index}] Failed to read frame.")
                break

            # Write to current segment
            self.out.write(frame)

            # Send compressed frame for preview
            if not self.frame_queue.full():
                ret_jpeg, jpeg_data = cv2.imencode(".jpg", frame)
                if ret_jpeg:
                    try:
                        self.frame_queue.put_nowait(jpeg_data.tobytes())
                    except queue.Full:
                        pass

            # Check if it’s time to start a new segment
            elapsed = time.time() - self.segment_start_time
            if elapsed >= self.settings["chunk_minutes"] * 60:
                self.start_new_segment()

            # Enforce approximate FPS timing
            if self.settings["fps"] > 0:
                time.sleep(1.0 / self.settings["fps"])

        # Cleanup
        self.stop_current_segment()
        self.cap.release()
        print(f"[Camera {self.camera_index}] Stopped recording.")

    def start_new_segment(self):
        """Close the existing file (if any) and start a new video segment."""
        self.stop_current_segment()  # ensure the old file is closed

        # Prepare a new segment
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        segment_filename = f"camera_{self.camera_index}_segment{self.segment_index}_{timestamp}.mp4"
        output_path = os.path.join(self.settings["output_dir"], segment_filename)

        # Retrieve actual resolution/fps
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.settings["fps"] if self.settings["fps"] > 0 else 30

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.out = cv2.VideoWriter(output_path, fourcc, actual_fps, (width, height))
        self.segment_start_time = time.time()

        print(f"[Camera {self.camera_index}] Starting new segment: {output_path} "
              f"({width}x{height}, {actual_fps} FPS)")
        self.segment_index += 1

    def stop_current_segment(self):
        """Release the current video file writer."""
        if self.out is not None:
            self.out.release()
            self.out = None

    def stop(self):
        """Signal the process to end."""
        self.stop_event.set()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-Camera Surveillance (Time-Chunks)")

        # 1) Discover cameras
        self.cameras_found = self.discover_cameras(max_test=10)

        # 2) UI tracking
        self.camera_checkboxes = []
        self.default_fps = 5
        self.default_width = 640
        self.default_height = 480
        self.default_chunk = 10  # 10 minutes

        self.output_directory = os.getcwd()

        # 3) Processes & queues
        self.processes = []
        self.queues = []

        # 4) Build GUI
        self.init_ui()

        # 5) Timer for updating previews
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_previews)

    def init_ui(self):
        # We'll put camera selection & preview in tabs
        central_widget = QWidget()
        main_vlayout = QVBoxLayout(central_widget)

        self.tabs = QTabWidget()
        main_vlayout.addWidget(self.tabs)

        # --- Tab 1: Camera Selection ---
        camera_tab = QWidget()
        camera_tab_layout = QFormLayout(camera_tab)

        if self.cameras_found:
            for cam_idx in self.cameras_found:
                cb = QCheckBox(f"Camera {cam_idx}")
                camera_tab_layout.addRow(cb)
                self.camera_checkboxes.append(cb)
        else:
            camera_tab_layout.addRow(QLabel("No cameras found."))

        self.tabs.addTab(camera_tab, "Cameras")

        # --- Tab 2: Live Preview ---
        preview_tab = QWidget()
        self.preview_layout = QHBoxLayout(preview_tab)

        self.preview_widgets = []
        for cam_idx in self.cameras_found:
            label = QLabel()
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("border: 1px solid black;")
            self.preview_layout.addWidget(label)
            self.preview_widgets.append(label)

        self.tabs.addTab(preview_tab, "Preview")

        # --- Settings area below the tabs ---
        settings_layout = QHBoxLayout()

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(0, 60)
        self.fps_spin.setValue(self.default_fps)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 3840)
        self.width_spin.setValue(self.default_width)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(0, 2160)
        self.height_spin.setValue(self.default_height)

        # Chunk duration
        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(1, 1440)  # 1 min to 24 hours
        self.chunk_spin.setValue(self.default_chunk)

        self.output_dir_btn = QPushButton("Select Output Directory")
        self.output_dir_btn.clicked.connect(self.select_output_dir)

        settings_layout.addWidget(QLabel("FPS(0=def):"))
        settings_layout.addWidget(self.fps_spin)
        settings_layout.addWidget(QLabel("W(0=def):"))
        settings_layout.addWidget(self.width_spin)
        settings_layout.addWidget(QLabel("H(0=def):"))
        settings_layout.addWidget(self.height_spin)
        settings_layout.addWidget(QLabel("Chunk Duration (min):"))
        settings_layout.addWidget(self.chunk_spin)
        settings_layout.addWidget(self.output_dir_btn)

        main_vlayout.addLayout(settings_layout)

        # --- Control buttons ---
        button_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Recording")
        self.start_btn.clicked.connect(self.start_recording)

        self.stop_btn = QPushButton("Stop Recording")
        self.stop_btn.clicked.connect(self.stop_recording)
        self.stop_btn.setEnabled(False)

        self.close_btn = QPushButton("Close App")
        self.close_btn.clicked.connect(self.close_app)

        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.close_btn)

        main_vlayout.addLayout(button_layout)

        self.setCentralWidget(central_widget)

    def discover_cameras(self, max_test=10):
        """Naive check of cameras from 0..max_test-1."""
        available = []
        for i in range(max_test):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                available.append(i)
            cap.release()
        return available

    def select_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Folder", os.getcwd())
        if directory:
            self.output_directory = directory

    def start_recording(self):
        selected = []
        for checkbox, idx in zip(self.camera_checkboxes, self.cameras_found):
            if checkbox.isChecked():
                selected.append(idx)

        if not selected:
            QMessageBox.warning(self, "No Cameras Selected", "Please select at least one camera.")
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.processes.clear()
        self.queues.clear()

        for idx in selected:
            frame_queue = multiprocessing.Queue(maxsize=2)
            self.queues.append((idx, frame_queue))

            settings = {
                "fps": self.fps_spin.value(),
                "width": self.width_spin.value(),
                "height": self.height_spin.value(),
                "output_dir": self.output_directory,
                "chunk_minutes": self.chunk_spin.value(),
            }

            p = CameraProcess(idx, settings, frame_queue)
            p.start()
            self.processes.append(p)

        # Switch to the Preview tab automatically
        self.tabs.setCurrentIndex(1)
        # Start updating previews
        self.timer.start(100)

    def stop_recording(self):
        # Stop preview updates first
        self.timer.stop()

        # Stop and join each process
        for p in self.processes:
            p.stop()
        for p in self.processes:
            p.join()

        self.processes.clear()
        self.queues.clear()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        # Clear previews
        for label in self.preview_widgets:
            label.clear()
            label.setText("Stopped")

    def update_previews(self):
        """Fetch frames from each queue and display them."""
        for (idx, q), label in zip(self.queues, self.preview_widgets):
            if not q.empty():
                try:
                    jpeg_bytes = q.get_nowait()
                    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        h, w, ch = frame.shape
                        bytes_per_line = w * ch
                        q_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format_BGR888)
                        pixmap = QPixmap.fromImage(q_img)
                        # Scale to label's current size, preserving aspect ratio
                        pixmap = pixmap.scaled(
                            label.size(),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation
                        )
                        label.setPixmap(pixmap)
                except queue.Empty:
                    pass

    def close_app(self):
        """Stop recording if active, then close the app."""
        if self.stop_btn.isEnabled():
            self.stop_recording()
        self.close()

    def closeEvent(self, event):
        """Ensure processes are stopped if user closes via the title bar."""
        if self.stop_btn.isEnabled():
            self.stop_recording()
        event.accept()


def main():
    multiprocessing.set_start_method("spawn", force=True)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
