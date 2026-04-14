# System Monitor
 
A Python application for real-time monitoring of system performance on **Linux (Ubuntu)**, with partial Windows support. Built as an engineering project.

## Features
 
**Real-time monitoring of critical system metrics:**
- CPU usage and frequency
- GPU utilization
- RAM usage
- Disk I/O activity
 
**Built-in stress tests:**
- CPU stress test
- RAM stress test
 
**Fully unit-tested with pytest and coverage reports**

## Installation
 
Clone the repository:
 
```bash
git clone https://github.com/AdamKow32/SystemMonitor.git
cd SystemMonitor
```
 
Install dependencies:
 
```bash
pip install .
```
 
## Usage
 
After installation, run from anywhere:
 
```bash
systemmonitor
```

## Requirements
 
- Python 3.10+
- Linux (Ubuntu recommended), partial Windows support
- Dependencies listed in `pyproject.toml`


## Tests
 
Run the test suite with:
 
```bash
pytest
```
 
To check code coverage:
 
```bash
pytest --cov
```
 
Coverage configuration is defined in `.coveragerc`. Test results and stress reports are available in the `stress_reports/` and `tests/` directories.
 

## Project Structure
 
```
SystemMonitor/
├── src/systemmonitor/   # Application source code
├── tests/               # Unit tests
├── stress_reports/      # Stress test output reports
├── pyproject.toml       # Project configuration and dependencies
├── .coveragerc          # Coverage configuration
└── README.md
```
 
## Engineering Thesis
 
This project was developed as part of an engineering thesis.
Download the full thesis (Polish):
[Praca_Inżynierska.pdf](https://github.com/user-attachments/files/25519468/Praca_Inzynierska.pdf)
 

## License
 
MIT License — see [LICENSE](LICENSE) for details.
 

## Author
 
Created by **Adam Kowalski**



