
import time
import json
import hashlib
import uuid
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from flask import Flask, request, jsonify, render_template_string

CHAIN_FILE = "chain.json"
DIFFICULTY = 3  # small number for classroom PoW (increase to make mining slower)


@dataclass
class Transaction:
    product_id: str
    from_role: str
    to_role: str
    location: str
    timestamp: float
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Block:
    index: int
    timestamp: float
    transactions: List[Dict[str, Any]]
    previous_hash: str
    nonce: int
    hash: str

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }


class Blockchain:
    def __init__(self, difficulty: int = DIFFICULTY):
        self.difficulty = difficulty
        self.chain: List[Block] = []
        self.current_transactions: List[Dict[str, Any]] = []
        self.load_chain()

    def new_transaction(self, tx: Transaction) -> int:
        self.current_transactions.append(tx.to_dict())
        # return index of the block that will hold this transaction (next block)
        return self.last_block.index + 1 if self.chain else 0

    @staticmethod
    def hash_block(index, timestamp, transactions, previous_hash, nonce) -> str:
        block_string = json.dumps({
            "index": index,
            "timestamp": timestamp,
            "transactions": transactions,
            "previous_hash": previous_hash,
            "nonce": nonce
        }, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def mine_block(self) -> Block:
        index = self.last_block.index + 1 if self.chain else 0
        timestamp = time.time()
        transactions = self.current_transactions.copy()  # include current txs
        previous_hash = self.last_block.hash if self.chain else "0" * 64
        nonce = 0

        prefix = "0" * self.difficulty
        while True:
            hash_val = self.hash_block(index, timestamp, transactions, previous_hash, nonce)
            if hash_val.startswith(prefix):
                break
            nonce += 1

        block = Block(index=index, timestamp=timestamp, transactions=transactions,
                      previous_hash=previous_hash, nonce=nonce, hash=hash_val)
        self.chain.append(block)
        self.current_transactions = []  # reset pending transactions
        self.save_chain()
        return block

    @property
    def last_block(self) -> Block:
        return self.chain[-1] if self.chain else None

    def to_dict(self):
        return [b.to_dict() for b in self.chain]

    def save_chain(self):
        with open(CHAIN_FILE, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def load_chain(self):
        try:
            with open(CHAIN_FILE, "r") as f:
                data = json.load(f)
                self.chain = [Block(**b) for b in data]
        except (FileNotFoundError, json.JSONDecodeError):
            # create genesis block
            genesis_block = Block(index=0, timestamp=time.time(), transactions=[],
                                  previous_hash="0" * 64, nonce=0,
                                  hash=self.hash_block(0, time.time(), [], "0" * 64, 0))
            self.chain = [genesis_block]
            self.save_chain()

    def get_history_for_product(self, product_id: str) -> List[Dict[str, Any]]:
        history = []
        for block in self.chain:
            for tx in block.transactions:
                if tx.get("product_id") == product_id:
                    history.append({
                        "block_index": block.index,
                        "block_hash": block.hash,
                        "timestamp": tx.get("timestamp"),
                        "from_role": tx.get("from_role"),
                        "to_role": tx.get("to_role"),
                        "location": tx.get("location"),
                        "notes": tx.get("notes")
                    })
        # also include pending (unmined) transactions
        for tx in self.current_transactions:
            if tx.get("product_id") == product_id:
                history.append({
                    "block_index": None,
                    "block_hash": None,
                    "timestamp": tx.get("timestamp"),
                    "from_role": tx.get("from_role"),
                    "to_role": tx.get("to_role"),
                    "location": tx.get("location"),
                    "notes": tx.get("notes"),
                    "pending": True
                })
        # sort by timestamp
        history.sort(key=lambda x: x["timestamp"])
        return history


# --- Flask app / API ---

app = Flask(__name__)
blockchain = Blockchain()


HOME_HTML = """
<!doctype html>
<title>Supply Chain Blockchain - Classroom Demo</title>
<h1>Supply Chain Blockchain (Demo)</h1>

<h2>Add a transaction</h2>
<form action="/add" method="post">
  Product ID: <input name="product_id" value="{}"><br>
  From Role: <input name="from_role" value="Farmer"><br>
  To Role: <input name="to_role" value="Wholesaler"><br>
  Location: <input name="location" value="Farm"><br>
  Notes: <input name="notes" value="Harvested"><br>
  <button type="submit">Add & Mine</button>
</form>

<h2>Lookup product</h2>
<form action="/product" method="get">
  Product ID: <input name="product_id" value=""><br>
  <button type="submit">Lookup</button>
</form>

<p>API endpoints:</p>
<ul>
<li>POST /add (json) -> add transaction then mine a block</li>
<li>GET /product/&lt;product_id&gt; -> view journey</li>
<li>GET /chain -> full chain</li>
</ul>
"""

@app.route("/", methods=["GET"])
def home():
    example_id = str(uuid.uuid4())[:8]
    return render_template_string(HOME_HTML.format(example_id))


@app.route("/add", methods=["POST"])
def add_transaction():
    # accept JSON or form data
    if request.is_json:
        payload = request.get_json()
    else:
        payload = request.form.to_dict()

    required = ["product_id", "from_role", "to_role", "location"]
    for r in required:
        if r not in payload or payload[r] == "":
            return jsonify({"error": f"Missing field: {r}"}), 400

    tx = Transaction(
        product_id=str(payload["product_id"]),
        from_role=str(payload["from_role"]),
        to_role=str(payload["to_role"]),
        location=str(payload["location"]),
        timestamp=time.time(),
        notes=str(payload.get("notes", ""))
    )
    blockchain.new_transaction(tx)

    # For classroom demo we mine immediately so the transaction is committed quickly
    block = blockchain.mine_block()
    return jsonify({
        "message": "Transaction added and mined into block",
        "block": block.to_dict()
    })


@app.route("/product/<product_id>", methods=["GET"])
def product_lookup(product_id):
    history = blockchain.get_history_for_product(product_id)
    if not history:
        return jsonify({"product_id": product_id, "history": [], "message": "No records found"}), 404
    # convert timestamps to readable form
    for h in history:
        h["readable_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(h["timestamp"]))
    return jsonify({"product_id": product_id, "history": history})


@app.route("/product", methods=["GET"])
def product_lookup_form():
    product_id = request.args.get("product_id", "")
    if not product_id:
        return home()
    return product_lookup(product_id)


@app.route("/chain", methods=["GET"])
def get_chain():
    return jsonify({"length": len(blockchain.chain), "chain": blockchain.to_dict()})


if __name__ == "__main__":
    # Development server; accessible at http://127.0.0.1:5000
    print("Starting Supply Chain Blockchain demo server...")
    print("Visit: http://127.0.0.1:5000")
    app.run(debug=True)
