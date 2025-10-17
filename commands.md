# create env
python -m venv .venv

# load env
source .venv/bin/activate.fish

# install requirements
pip install -r requirements.txt

# compile java files
javac -d out $(find . -name "*.java")

# run java files
java -cp out edu.mci.exam.Main
