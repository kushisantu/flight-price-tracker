# Reproduce the DOT paid-fare model from the repo root.
# Windows without make: cd backend && .venv/Scripts/python.exe -m scripts.train_phase2

.PHONY: load train eval train-empirical eval-empirical eval-parser

load:
	cd backend && .venv/Scripts/python.exe -m scripts.load_db1b

train:
	cd backend && .venv/Scripts/python.exe -m scripts.train_phase2

eval:
	cd backend && .venv/Scripts/python.exe -m scripts.eval_phase2

train-empirical:
	cd backend && .venv/Scripts/python.exe -m scripts.train

eval-empirical:
	cd backend && .venv/Scripts/python.exe -m scripts.eval

eval-parser:
	cd backend && .venv/Scripts/python.exe -m scripts.eval_parser
