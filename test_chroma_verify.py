import chromadb
import numpy as np

# Test PersistentClient
c = chromadb.PersistentClient(path='./test_chroma_verify')
try:
    c.delete_collection('test_verify')
except:
    pass

coll = c.create_collection('test_verify', metadata={'hnsw:space': 'cosine'})
print('Collection created')

emb = np.random.randn(5, 512).astype(np.float32).tolist()
coll.add(ids=['a1', 'b2', 'c3', 'd4', 'e5'], embeddings=emb, documents=['x'] * 5)
print('Documents added')

r = coll.query(query_embeddings=[emb[0]], n_results=2)
print('Query OK!', r['ids'])
print('PersistentClient FULLY WORKS!')
