#!/usr/bin/env python3
"""
This script loads GloVe embeddings of a specified
dimension and the training data from the CodaLab
competition.

It uses a script found at https://gist.github.com/tokestermw/cb87a97113da12acb388
to pre-process emoticons, hashtags and user names.

It separates the data into training and testing sets of both
has_emotion and no_emotion partitions on ONE specified emotion and combines
the the tokenized corpus of tweets with the corresponding GloVe embeddings
and saves them as pickles so that they can be consumed by tf_binary_clf.py

"""
import numpy as np
import pandas as pd
import pickle
import re

INTENDED_EMBEDDING_DIMENSION = 50
MAX_TWEET_LENGTH = 35
PAD_TOKEN = 0
FLAGS = re.MULTILINE | re.DOTALL
GLOVE_LIMIT = 20000


def fix_split(pattern, string):
    splits = list((m.start(), m.end()) for m in re.finditer(pattern, string))
    starts = [0] + [i[1] for i in splits]
    ends = [i[0] for i in splits] + [len(string)]
    return [string[start:end] for start, end in zip(starts, ends)]


def hashtag(text):
    text = text.group()
    hashtag_body = text[1:]
    if hashtag_body.isupper():
        result = " {} ".format(hashtag_body.lower())
    else:
        result = " ".join(["<hashtag>"] + fix_split(r"(?=[A-Z])", hashtag_body))  # , flags=FLAGS))
    return result


def allcaps(text):
    text = text.group()
    return text.lower() + " <allcaps>"


def tokenize(text):
    # Different regex parts for smiley faces
    eyes = r"[8:=;]"
    nose = r"['`\-]?"

    def re_sub(pattern, repl):
        return re.sub(pattern, repl, text, flags=FLAGS)

    text = re_sub(r"https?:\/\/\S+\b|www\.(\w+\.)+\S*", "<url>")
    text = re_sub(r"@\w+", "<user>")
    text = re_sub(r"{}{}[)dD]+|[)dD]+{}{}".format(eyes, nose, nose, eyes), "<smile>")
    text = re_sub(r"{}{}p+".format(eyes, nose), "<lolface>")
    text = re_sub(r"{}{}\(+|\)+{}{}".format(eyes, nose, nose, eyes), "<sadface>")
    text = re_sub(r"{}{}[\/|l*]".format(eyes, nose), "<neutralface>")
    text = re_sub(r"/", " / ")
    text = re_sub(r"<3", "<heart>")
    text = re_sub(r"[-+]?[.\d]*[\d]+[:,.\d]*", "<number>")
    text = re_sub(r"#\S+", hashtag)
    text = re_sub(r"([!?.]){2,}", r"\1 <repeat>")
    text = re_sub(r"\b(\S*?)(.)\2{2,}\b", r"\1\2 <elong>")
    text = re_sub(r"([A-Z]){2,}", allcaps)

    return text.lower()


def clean_and_separate(data, emotion):
    data['Tweet'] = data['Tweet'].apply(tokenize)

    has_emo_tweet = data[data[emotion] == 1]['Tweet']
    no_emo_tweet = data[data[emotion] == 0]['Tweet']

    has_emo_tweet.reset_index(drop=True, inplace=True)
    no_emo_tweet.reset_index(drop=True, inplace=True)

    has_emo_list = has_emo_tweet.values.tolist()
    no_emo_list = no_emo_tweet.values.tolist()

    return has_emo_list, no_emo_list


def create_train_and_test(has_emo, no_emo, test_size=0.2):
    has_emo_test_size = int(test_size * len(has_emo))
    no_emo_test_size = int(test_size * len(no_emo))

    test_has_emo = has_emo[: has_emo_test_size, :]
    test_no_emo = no_emo[: no_emo_test_size, :]

    train_has_emo = has_emo[has_emo_test_size:, :]
    train_no_emo = no_emo[no_emo_test_size:, :]

    return train_has_emo, train_no_emo, test_has_emo, test_no_emo


# This function was experimented with to see if balancing the dataset
# would help. It was not used in the data reported
def balance_data_set(input_df, emotion):
    # split by label
    has_emo_df = input_df[input_df[emotion] == 1]
    no_emo_df = input_df[input_df[emotion] == 0]
    smallest = min([len(no_emo_df), len(has_emo_df)])
    emo_samples = has_emo_df.sample(smallest)
    no_emo_samples = no_emo_df.sample(smallest)
    combined_df = pd.concat([emo_samples, no_emo_samples])
    combined_df = combined_df.sample(frac=1).reset_index(drop=True)
    return combined_df


def main():
    # Load up the GLOVE and split into words and vectors

    glove_filepath = "/Users/stevehof/school/comp/Word_Embedding_Files/" \
                     "glove.twitter.27B/glove.twitter.27B." + \
                     str(INTENDED_EMBEDDING_DIMENSION) + "d.txt"
    word_to_index = {'PAD': PAD_TOKEN}
    weights = []

    with open(glove_filepath, 'r', encoding='UTF-8') as f:
        for index, line in enumerate(f):

            values = line.split()  # word and weights separated by space
            word = values[0]  # word is first symbol on each line
            word_weights = np.asarray(values[1:], dtype=np.float32)  # remainder of line is weights for words
            if len(word_weights) != INTENDED_EMBEDDING_DIMENSION:
                continue
            word_to_index[word] = index + 1  # PAD is zeroth index so shift by one
            weights.append(word_weights)
            if len(word_weights) != INTENDED_EMBEDDING_DIMENSION:
                print(f"messing up at index {index}")
                print(f"index {index} is length {len(word_weights)}")

            # if index + 1 == GLOVE_LIMIT:
                # # Limit size for now
                # break

    # Insert PADDING at index 0.
    embedding_dimension = len(weights[0])
    weights.insert(0, np.random.randn(embedding_dimension))

    # Append unknown and pad to end of vocab
    UNKNOWN_TOKEN = len(weights)
    word_to_index['UNK'] = UNKNOWN_TOKEN

    # Create matrix in proper shape for embeddings and initialize to zero
    weights.append(np.random.randn(embedding_dimension))

    # Construct final vocab
    weights = np.asarray(weights, dtype=np.float32)

    # Import and clean data
    train_df = pd.read_csv('training_data/2018-E-c-En-train.txt',
                           sep='\t',
                           quoting=3,
                           lineterminator='\r')

    val_df = pd.read_csv('training_data/2018-E-c-En-dev.txt',
                         sep='\t',
                         quoting=3,
                         lineterminator='\r')

    test_df = pd.read_csv('training_data/2018-E-c-En-test.txt',
                          sep='\t',
                          quoting=3,
                          lineterminator='\r')

    df = train_df.append(val_df, ignore_index=True)

    emotion = 'anger'  # emotion for testing on
    df = df[['Tweet', emotion]]
    df.dropna(axis=0, inplace=True)
    # df = balance_data_set(df, emotion)
    df.reset_index(drop=True, inplace=True)

    has_emo_tweets, no_emo_tweets = clean_and_separate(df, emotion)
    num_has_emo, num_no_emo = len(has_emo_tweets), len(no_emo_tweets)

    # turn tweets into word embedding vectors
    has_emo_ids = np.zeros((num_has_emo, MAX_TWEET_LENGTH), dtype='int32')
    tweet_counter = 0
    for tweet in has_emo_tweets:
        index_counter = 0
        split = tweet.split()
        for word in split:
            try:
                has_emo_ids[tweet_counter][index_counter] = word_to_index[word]
            except KeyError:
                has_emo_ids[tweet_counter][index_counter] = word_to_index['UNK']
            index_counter += 1
            if index_counter >= MAX_TWEET_LENGTH:
                break
        tweet_counter += 1

    # do same for no_emo tweets
    no_emo_ids = np.zeros((num_no_emo, MAX_TWEET_LENGTH), dtype='int32')
    tweet_counter = 0
    for tweet in no_emo_tweets:
        index_counter = 0
        split = tweet.split()
        for word in split:
            try:
                no_emo_ids[tweet_counter][index_counter] = word_to_index[word]
            except KeyError:
                no_emo_ids[tweet_counter][index_counter] = UNKNOWN_TOKEN
            index_counter += 1
            if index_counter >= MAX_TWEET_LENGTH:
                break
        tweet_counter += 1

    # save and dump into pickle
    train_has_emo, train_no_emo, test_has_emo, test_no_emo = create_train_and_test(has_emo_ids, no_emo_ids)
    pickle_path = "pre_processed_pickles/" + str(emotion) + "/vocab_size-" + str(
        GLOVE_LIMIT) + "balanced_tweet_data_" + str(
        INTENDED_EMBEDDING_DIMENSION) + "d.pickle"
    with open(pickle_path, 'wb') as f:
        pickle.dump([train_has_emo, train_no_emo, test_has_emo, test_no_emo, weights], f)


if __name__ == '__main__':
    main()
