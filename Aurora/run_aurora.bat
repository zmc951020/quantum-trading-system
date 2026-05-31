@echo off
cd /d "D:\Gupiao\量化交易测试设备方案\攒机\最后评估01\DS-V3.2T量化交易专用工作站配置深度研判与采购决策报告02_files\攒机配置\Aurora"
python production_start.py
echo Aurora stopped at %date% %time% >> aurora_service.log
