import os

import numpy as np
import tensorflow as tf
from keras.preprocessing.sequence import pad_sequences
from keras.models import Sequential
from keras.layers import Embedding, LSTM, Dense
from multiprocessing import Process, Queue
from keras.preprocessing.text import Tokenizer
import json

# Sample Solidity contracts and labels (replace with your data)
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
path = f"{ROOT}\\contracts\\"  # temp data set
# path = f"{ROOT}\\contracts\\" # main data set

labels = []
contracts = []
output_name = 'icse20'
duration_stat = {}
tools = ['mythril', 'securify', 'maian', 'manticore', 'honeybadger']
count = {}
output = {}

# Sample dataset (replace with your dataset)
# contracts = [
#     "contract A { function foo() public {} }",
#     "contract B { function bar() public {} }",
#     # ...
# ]

# Sample labels (replace with your labels)
# labels = [1, 0, 1, 0, 1, ...]

# Split the dataset into training and testing sets


def get_result_vulnarable(contract):
    total_duration = 0
    res = False
    for tool in tools:
        path_result = os.path.join(f"{ROOT}\\results\\", tool, output_name, contract, 'result.json')
        if not os.path.exists(path_result):
            continue
        with open(path_result, 'r', encoding='utf-8') as fd:
            data = None
            try:
                data = json.load(fd)
            except Exception as a:
                continue
            if tool not in duration_stat:
                duration_stat[tool] = 0
            if tool not in count:
                count[tool] = 0
            count[tool] += 1
            duration_stat[tool] += data['duration']
            total_duration += data['duration']

            if contract not in output:
                output[contract] = {
                    'tools': {},
                    'lines': set(),
                    'nb_vulnerabilities': 0
                }
            output[contract]['tools'][tool] = {
                'vulnerabilities': {},
                'categories': {}
            }
            if data['analysis'] is None:
                continue
            if tool == 'mythril':
                analysis = data['analysis']
                if analysis['issues'] is not None:
                    for result in analysis['issues']:
                        vulnerability = result['title'].strip()
                        res = True
            elif tool == 'oyente' or tool == 'osiris':
                for analysis in data['analysis']:
                    if analysis['errors'] is not None:
                        for result in analysis['errors']:
                            vulnerability = result['message'].strip()
                            res = True
            elif tool == 'manticore':
                for analysis in data['analysis']:
                    for result in analysis:
                        vulnerability = result['name'].strip()
                        res = True
            elif tool == 'maian':
                for vulnerability in data['analysis']:
                    if data['analysis'][vulnerability]:
                        res = True
            elif tool == 'securify':
                for f in data['analysis']:
                    analysis = data['analysis'][f]['results']
                    for vulnerability in analysis:
                        for line in analysis[vulnerability]['violations']:
                            res = True
            elif tool == 'slither':
                analysis = data['analysis']
                for result in analysis:
                    vulnerability = result['check'].strip()
                    line = None
                    if 'source_mapping' in result['elements'][0] and len(
                            result['elements'][0]['source_mapping']['lines']) > 0:
                        line = result['elements'][0]['source_mapping']['lines'][0]
                        res = True
            elif tool == 'smartcheck':
                analysis = data['analysis']
                for result in analysis:
                    vulnerability = result['name'].strip()
                    res = True
            elif tool == 'solhint':
                analysis = data['analysis']
                for result in analysis:
                    vulnerability = result['type'].strip()
                    res = True
            elif tool == 'honeybadger':
                for analysis in data['analysis']:
                    if analysis['errors'] is not None:
                        for result in analysis['errors']:
                            vulnerability = result['message'].strip()
                            res = True
    return res


def read_text_file(file_path, name):
    with open(file_path, encoding="utf8") as f:
        smartContractContent = f.read()
        isVulnarable = get_result_vulnarable(name)
        contracts.append(smartContractContent)
        isVal = 0
        if (isVulnarable):
            isVal = 1

        labels.append(isVal)

os.chdir(path)

for file in os.listdir():
    # Check whether file is in text format or not
    if file.endswith(".sol"):
        file_path = f"{path}\{file}"
        name = file.replace(".sol", "")
        read_text_file(file_path, name)

tokenizer = Tokenizer()
split_ratio = 0.8
split_index = int(len(contracts) * split_ratio)

train_contracts, test_contracts = contracts[:split_index], contracts[split_index:]
train_labels, test_labels = labels[:split_index], labels[split_index:]


def tokenize_and_preprocess_data(contracts, labels, result_queue):
    tokenizer.fit_on_texts(contracts)
    sequences = tokenizer.texts_to_sequences(contracts)
    max_sequence_length = max([len(seq) for seq in sequences])

    X = pad_sequences(sequences, maxlen=max_sequence_length, padding='post')
    y = np.array(labels)

    result_queue.put((X, y))


result_queue = Queue()

# Create processes for data preprocessing
train_process = Process(target=tokenize_and_preprocess_data, args=(train_contracts, train_labels, result_queue))
test_process = Process(target=tokenize_and_preprocess_data, args=(test_contracts, test_labels, result_queue))

# Start processes
train_process.start()
test_process.start()

# Wait for processes to finish
train_process.join()
test_process.join()

# Retrieve data from the queue
X_train, y_train = result_queue.get()
X_test, y_test = result_queue.get()


def train_model(X_train, y_train):
    # Build an LSTM model
    model = Sequential()
    model.add(Embedding(input_dim=len(tokenizer.word_index) + 1, output_dim=64, input_length=X_train.shape[1]))
    model.add(LSTM(128))
    model.add(Dense(1, activation='sigmoid'))

    model.compile(loss='binary_crossentropy', optimizer='adam', metrics=['accuracy'])

    # Train the model
    model.fit(X_train, y_train, epochs=10, batch_size=32)

    return model


# Train the model in a separate process
model_process = Process(target=train_model, args=(X_train, y_train))
model_process.start()
model_process.join()

# Evaluate the model
loss, accuracy = model_process.get()
print(f"Test Loss: {loss}, Test Accuracy: {accuracy}")





