# Multi-Camera Surveillance with Time-Chunks

This project provides a Python-based application for managing multi-camera surveillance systems. The application allows users to record videos from multiple cameras, preview live camera feeds, and save recordings in time-chunked segments.

## Features

- Supports multiple cameras simultaneously.
- Adjustable recording settings:
  - Frames per second (FPS)
  - Resolution (Width x Height)
  - Time-chunk duration (minutes)
- Live preview of camera feeds.
- Automatic file segmentation for easier storage and retrieval.
- Intuitive GUI built with PySide6.
- Saves recordings in the specified output directory.

## Prerequisites

Ensure the following dependencies are installed:

- Python 3.8 or later
- PySide6
- OpenCV
- NumPy

You can install the required Python packages with:
```bash
pip install PySide6 opencv-python numpy
```

## Usage

### Running the Application
1. Clone the repository:
   ```bash
   git clone <repository_url>
   cd <repository_directory>
   ```
2. Run the application:
   ```bash
   python main.py
   ```

### GUI Overview

1. **Cameras Tab**
   - Displays detected cameras.
   - Use checkboxes to select cameras for recording.

2. **Preview Tab**
   - Shows live previews of selected cameras.

3. **Settings**
   - Adjust FPS, resolution, and chunk duration.
   - Select an output directory for saving recordings.

4. **Control Buttons**
   - **Start Recording**: Begin recording from selected cameras.
   - **Stop Recording**: Stop recording and close active processes.
   - **Close App**: Stop recording (if active) and exit the application.

### Key Settings

- FPS: Frames per second (0 uses the camera's default).
- Width and Height: Resolution for video recording (0 uses the camera's default).
- Chunk Duration: Length of each video segment in minutes.
- Output Directory: Directory where video files are saved.

## Code Overview

### Key Components

- `CameraProcess`: A multiprocessing class to manage individual camera streams. Each camera runs in its own process to ensure smooth performance.
- `MainWindow`: The main application window with tabs for camera selection, live preview, and settings.
- `discover_cameras`: Function to detect available cameras.
- `start_new_segment`: Creates new video files based on the specified chunk duration.
- `update_previews`: Updates live preview feeds using frames from the camera processes.

### How It Works
1. The application detects available cameras.
2. Users select cameras and set desired recording parameters.
3. Each camera is managed by a separate process to record video chunks and update live previews.
4. The application saves recordings in `.mp4` format in the specified directory.

## Example Output Structure

```
output_directory/
├── camera_0_segment0_20250121_120000.mp4
├── camera_0_segment1_20250121_121000.mp4
├── camera_1_segment0_20250121_120000.mp4
└── camera_1_segment1_20250121_121000.mp4
```

## Known Issues

- Preview updates may lag with high FPS settings or slow hardware.
- If no cameras are detected, ensure the cameras are properly connected and drivers are installed.

## Contributing

Feel free to open issues or submit pull requests to enhance the functionality.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
