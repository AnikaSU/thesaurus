import asyncio
import pickle
import timeit
import dill
import numpy as np

from thesaurus import fetch_list_of_words, Word

# l = ['good','bad','apple','evil','man','kind','cup','orange','fine','worse','ok','yellow','mug','grass','green','women']
l = []
vocab = list(np.load('join_vocab.npy'))
for i,word in enumerate(vocab,1):
    l.append(word.replace('_',' '))
    if i >= 30000:
        break
# l = ['natural gas']
start = timeit.default_timer()
words_dict = asyncio.run(fetch_list_of_words(l))
stop = timeit.default_timer()
print(words_dict)
with open('join_vocab.pickle','wb') as f:
    dill.dump(words_dict,f)
print('Time: ', stop - start)

# with open('thesauri.pickle','rb') as f:
#     thesauri = dill.load(f)
# print(thesauri)