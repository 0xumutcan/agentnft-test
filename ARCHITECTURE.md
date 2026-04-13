# zkML Proof-Gated NFT — Teknik Mimari
**Platform:** Abstract L2 | **Proof sistemi:** EZKL | **Puzzle:** On-chain ARG

---

## 1. Kavramsal Özet

```
[On-chain ipuçları]  →  [Agent: ipuçları topla]  →  [LLM: cevabı çıkar]
       ↓                                                      ↓
[Abstract L2]    ←  [NFT mint (ERC-721)]  ←  [EZKL proof: cevap doğru]
```

Blockchain'e gömülü ipuçlarını bir AI agent okur, LLM ile cevabı çıkarır,
küçük bir EZKL-MLP "bu cevap doğru" diye kanıtlar, Abstract L2'deki
verifier kontratı proof'u kabul ederse NFT mint edilir.

---

## 2. Proje Yapısı

```
zkml-nft/
├── contracts/                  # Solidity (Foundry)
│   ├── src/
│   │   ├── ZkMLNFT.sol         # ERC-721 NFT kontratı
│   │   ├── PuzzleRegistry.sol  # Puzzle & ipucu yönetimi
│   │   └── verifiers/
│   │       └── Halo2Verifier.sol  # EZKL tarafından üretilir
│   ├── script/
│   │   ├── Deploy.s.sol
│   │   └── SeedPuzzle.s.sol    # İpuçlarını on-chain yükler
│   ├── test/
│   └── foundry.toml
│
├── ml/                         # Python zkML pipeline
│   ├── model.py                # MLP tanımı (PyTorch)
│   ├── train.py                # Eğitim scripti
│   ├── ezkl_pipeline.py        # compile → setup → verifier
│   ├── generate_proof.py       # Tek proof üretimi (agent çağırır)
│   └── artifacts/
│       ├── model.onnx
│       ├── settings.json       # EZKL devre ayarları
│       ├── pk.key              # Proving key
│       ├── vk.key              # Verifying key
│       └── verifier.sol        # → contracts/src/verifiers/ kopyalanır
│
├── agent/                      # Otonom puzzle-çözücü agent
│   ├── main.py                 # Giriş noktası
│   ├── clue_reader.py          # On-chain ipuçlarını okur (web3.py)
│   ├── llm_reasoner.py         # LLM ile cevap çıkarır (Anthropic SDK)
│   ├── prover.py               # EZKL proof üretir
│   ├── minter.py               # Abstract L2'ye tx gönderir
│   └── config.py
│
├── puzzles/                    # Puzzle tanımları (off-chain kaynak)
│   └── puzzle_001.json
│
├── .env.example
└── README.md
```

---

## 3. Smart Contract Katmanı

### 3.1 PuzzleRegistry.sol

```solidity
struct Puzzle {
    bytes32 id;
    address verifier;       // EZKL Halo2Verifier adresi
    uint256 clueCount;
    bool active;
    string metadataURI;     // NFT metadata şablonu
}

struct Clue {
    uint8 clueType;         // 0=TEXT, 1=HINT, 2=ELIMINATION, 3=CONTEXT
    bytes data;             // ABI-encode edilmiş içerik
    uint256 index;
}

// Eventler — agent bunları okur
event ClueDeposited(bytes32 indexed puzzleId, uint256 index, uint8 clueType, bytes data);
event PuzzleCreated(bytes32 indexed puzzleId, address verifier);
```

**Neden eventler?** Agent `eth_getLogs` ile tüm ipuçlarını tek sorguda çeker.
Calldata'ya göre daha verimli ve standart.

### 3.2 ZkMLNFT.sol (ERC-721)

```solidity
function mintWithProof(
    bytes32 puzzleId,
    bytes calldata proof,
    uint256[] calldata publicInputs
) external {
    // 1. Bu puzzle için verifier'ı al
    address verifier = registry.getVerifier(puzzleId);
    
    // 2. EZKL verifier'ı çağır
    require(IHalo2Verifier(verifier).verify(proof, publicInputs), "Invalid proof");
    
    // 3. Aynı puzzle için tekrar mint engelle (per-puzzle, per-wallet)
    require(!claimed[msg.sender][puzzleId], "Already claimed");
    claimed[msg.sender][puzzleId] = true;
    
    // 4. Mint
    _safeMint(msg.sender, _nextTokenId++);
}
```

### 3.3 Abstract L2 Özellikleri

Abstract'ın native AA (EIP-4337 benzeri) özelliğini agent için kullanacağız:
- Agent bir EOA yerine **AbstractAccount** kontratı üzerinden işlem yapar
- Paymaster entegrasyonu: agent'ın gas için ETH bulundurması gerekmez (isteğe bağlı)

---

## 4. EZKL/zkML Katmanı

### 4.1 Model Seçimi: Embedding Similarity MLP

**Neden bu model?**
- EZKL için pratik boyut: <10k parametre
- Sentence embedding (384-dim) → normalize → MLP → [0,1] skor
- Full transformer EZKL'de çalışmaz (çok büyük devre)

**Mimari:**
```
Input: sentence_embedding [384]  ← sentence-transformers dışında üretilir
  ↓
Linear(384 → 64) + ReLU
  ↓
Linear(64 → 32) + ReLU
  ↓
Linear(32 → 1) + Sigmoid
  ↓
Output: correctness_score [0,1]  ← threshold: 0.7
```

**Kritik tasarım kararı:**
Embedding hesabı ZK devre dışında yapılır. ZK devresi sadece
"bu embedding verildiğinde model 0.7+ skor üretiyor" iddiasını kanıtlar.
Bu yüzden public input = embedding (gizli değil), output = skor.

### 4.2 Eğitim Verisi

Her puzzle için:
```python
positives = [
    embed("doğru cevap"),
    embed("doğru cevabın sinonimi"),
    embed("semantically equivalent ifade"),
    # ~20 pozitif örnek
]
negatives = [
    embed("alakasız şeyler"),
    embed("yakın ama yanlış cevaplar"),
    embed("adversarial örnekler"),
    # ~50 negatif örnek
]
```

**Her puzzle için ayrı model ağırlıkları** → ayrı verifier kontratı.

### 4.3 EZKL Pipeline

```bash
# 1. ONNX export
python ml/train.py --puzzle puzzle_001

# 2. EZKL ayarları (devre boyutu kalibrasyonu)
ezkl gen-settings -M model.onnx -O settings.json
ezkl calibrate-settings -M model.onnx -D sample_input.json -S settings.json

# 3. Devre derleme
ezkl compile-circuit -M model.onnx -S settings.json -O circuit.compiled

# 4. KZG setup (SRS gerekli)
ezkl get-srs -S settings.json

# 5. Proving/Verifying key üretimi
ezkl setup -M circuit.compiled --srs-path kzg.srs -V vk.key -P pk.key

# 6. EVM Verifier Solidity kodu üret
ezkl create-evm-verifier -V vk.key --srs-path kzg.srs -S settings.json --sol-code-path verifier.sol
```

### 4.4 Proof Üretimi (Agent tarafından runtime'da)

```bash
# Witness üret
ezkl gen-witness -M circuit.compiled -D input.json -O witness.json

# Proof üret (~30-120 saniye)
ezkl prove -M circuit.compiled -W witness.json -P pk.key --proof-path proof.json

# Verify (opsiyonel, kontrol için)
ezkl verify --proof-path proof.json -V vk.key
```

---

## 5. Agent Katmanı

### 5.1 Ana Akış

```python
async def run_agent(puzzle_id: str):
    # 1. On-chain ipuçlarını topla
    clues = await clue_reader.fetch_clues(puzzle_id)
    # → ClueDeposited eventlerini parse eder
    # → Her clue'nun tipine göre yapılandırır

    # 2. LLM ile cevap çıkar
    answer = await llm_reasoner.reason(clues)
    # → System prompt: "Sen bir blockchain puzzle çözücüsüsün..."
    # → İpuçlarını yapılandırılmış format'ta LLM'e ver
    # → Chain-of-thought ile cevabı çıkar

    # 3. Embedding hesapla (EZKL dışında)
    embedding = embed(answer)  # sentence-transformers

    # 4. EZKL proof üret
    proof, public_inputs = await prover.prove(puzzle_id, embedding)

    # 5. Mint tx gönder
    tx_hash = await minter.mint(puzzle_id, proof, public_inputs)
    print(f"NFT minted: {tx_hash}")
```

### 5.2 İpucu Formatı (On-chain)

İpuçları ABI-encoded `bytes` olarak event'te yayınlanır:

```solidity
// TEXT tipi ipucu
bytes memory clueData = abi.encode(
    "Bu kavram, merkeziyetsiz sistemlerin temelindeki matematiksel garantiyi sağlar."
);

// HINT tipi ipucu (semantic yön)
bytes memory clueData = abi.encode(
    "Cevap: bir isim, teknoloji değil prensip"
);

// ELIMINATION tipi
bytes memory clueData = abi.encode(
    "Blockchain değil. Consensus değil. Daha temelde."
);
```

Agent bu tipleri decode ederek yapılandırılmış bir prompt oluşturur.

### 5.3 LLM Reasoning Prompt Şablonu

```
Sen bir on-chain puzzle çözücü agentsın.
Aşağıdaki ipuçları Abstract L2 blockchain'inden okunmuştur.

=== PUZZLE #{puzzle_id} ===

[TEXT İpuçları]
{text_clues}

[Yön İpuçları]
{hint_clues}

[Eleme İpuçları]
{elimination_clues}

[Bağlam]
{context_clues}

Tüm ipuçlarını analiz ederek TEK BİR KAVRAM veya KELİME cevabını ver.
Cevabın semantik alanda doğrulanacak, tam eşleşme gerekmez.
Adım adım düşün, sonra sadece cevabı yaz.
```

---

## 6. Veri Akışı (End-to-End)

```
[Puzzle Creator]
    │
    ├─ 1. ML modeli eğit (puzzle'a özel MLP)
    ├─ 2. EZKL ile verifier.sol üret
    ├─ 3. Verifier kontratını Abstract L2'ye deploy et
    ├─ 4. PuzzleRegistry'e puzzle kaydını oluştur
    └─ 5. İpuçlarını on-chain yükle (ClueDeposited events)

[Agent — Otonom]
    │
    ├─ 1. ClueDeposited eventlerini oku (eth_getLogs)
    ├─ 2. İpuçlarını decode et ve yapılandır
    ├─ 3. LLM'e gönder → cevap al
    ├─ 4. sentence-transformers ile embedding hesapla
    ├─ 5. EZKL ile proof üret (~1-2 dk)
    └─ 6. mintWithProof() tx'ini Abstract L2'ye gönder

[Abstract L2 Kontratı]
    │
    ├─ 1. Puzzle'ın verifier adresini PuzzleRegistry'den al
    ├─ 2. Halo2Verifier.verify(proof, publicInputs) çağır
    ├─ 3. ✓ Valid → NFT mint
    └─ 4. ✗ Invalid → revert
```

---

## 7. Teknik Riskler ve Kararlar

| Risk | Etki | Karar |
|------|------|-------|
| EZKL devre boyutu | Proving süresi uzar, gas artar | 384→64→32→1 MLP, k=14 |
| Embedding off-circuit | Güvenlik zayıflığı | Public input, açıkça kabul edilmiş trade-off |
| Her puzzle ayrı verifier | Deploy maliyeti | Kabul — research projesi |
| LLM cevap tutarsızlığı | Agent başarısız olur | Threshold 0.7, retry mekaniği |
| Abstract L2 verifier gas | Halo2 verification pahalı | Abstract'ın düşük gas maliyeti yeterli |

---

## 8. İmplementasyon Sırası

### Faz 1 — ML Pipeline (2-3 gün)
1. `ml/model.py` — MLP tanımı
2. `ml/train.py` — puzzle_001 için eğitim
3. `ml/ezkl_pipeline.py` — ONNX → EZKL → verifier.sol
4. Local proof testi

### Faz 2 — Smart Contracts (1-2 gün)
1. `PuzzleRegistry.sol` + testler
2. `ZkMLNFT.sol` + testler
3. EZKL verifier entegrasyonu
4. Abstract L2 testnet deploy

### Faz 3 — Agent (1-2 gün)
1. `clue_reader.py` — on-chain veri okuma
2. `llm_reasoner.py` — Anthropic SDK entegrasyonu
3. `prover.py` — EZKL subprocess wrapper
4. `minter.py` — Abstract L2 tx

### Faz 4 — İlk Puzzle + Test (1 gün)
1. puzzle_001.json tasarla
2. İpuçlarını on-chain yükle
3. Agent'ı çalıştır, uçtan uca test

---

## 9. Bağımlılıklar

```
# Python
torch>=2.0
onnx
ezkl>=9.0
sentence-transformers
web3>=6.0
anthropic>=0.25
python-dotenv

# Solidity
forge (Foundry)
openzeppelin-contracts@5.x

# Node (opsiyonel, script için)
ethers@6.x
```

---

## 10. Ortam Değişkenleri (.env)

```
ABSTRACT_RPC=https://api.testnet.abs.xyz
PRIVATE_KEY=0x...
ANTHROPIC_API_KEY=sk-ant-...
PUZZLE_REGISTRY_ADDRESS=0x...
NFT_CONTRACT_ADDRESS=0x...
```
