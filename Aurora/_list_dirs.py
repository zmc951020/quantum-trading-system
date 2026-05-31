import os
dirs = ['ems', 'oms', 'signals', 'risk', 'strategies', 'monitor', 'monitoring', 'config', 'models', 'ml', 'tools', 'utils', 'web', 'auto_backtest', 'experiments']
for d in dirs:
    if os.path.exists(d):
        files = os.listdir(d)
        print(f"\n=== {d}/ ({len(files)} files) ===")
        for f in files:
            print(f"  {f}")
    else:
        print(f"\n=== {d}/ MISSING ===")