@echo off
cd /d C:\Users\ben\OneDrive\Desktop\testing\automated_testing
python 3_long_term_bacnet_scrape_test.py --api-url http://192.168.204.16:8000 --frontend-url http://192.168.204.16 --once --check-faults >> overnight_bacnet.log 2>&1
