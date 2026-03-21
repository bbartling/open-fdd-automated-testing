@echo off
cd /d C:\Users\ben\OneDrive\Desktop\testing\automated_testing
python automated_suite.py --api-url http://192.168.204.16:8000 --frontend-url http://192.168.204.16 --bacnet-devices 3456789 3456790 --long-run-check-faults >> automated_suite.log 2>&1
