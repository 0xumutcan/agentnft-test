// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title PuzzleRegistry
/// @notice Stores puzzles and broadcasts on-chain clues as events.
///         Agents discover clues by querying ClueDeposited event logs.
contract PuzzleRegistry {
    // ─── Clue types ───────────────────────────────────────────────────────────
    uint8 public constant TYPE_TEXT        = 0; // Plain natural-language clue
    uint8 public constant TYPE_HINT        = 1; // Semantic direction hint
    uint8 public constant TYPE_ELIMINATION = 2; // What the answer is NOT
    uint8 public constant TYPE_CONTEXT     = 3; // Background / domain context
    uint8 public constant TYPE_POINTER     = 4; // Points to another on-chain source

    // ─── Storage ──────────────────────────────────────────────────────────────
    struct Puzzle {
        address verifier;    // EZKL Halo2Verifier contract address
        uint256 clueCount;
        bool    active;
        string  metadataURI; // base URI for NFT metadata
    }

    address public owner;
    mapping(bytes32 => Puzzle) public puzzles;
    bytes32[] public puzzleIds;

    // ─── Events (agents listen to these) ─────────────────────────────────────
    event PuzzleCreated(
        bytes32 indexed puzzleId,
        address verifier,
        string  metadataURI
    );

    /// @notice Primary discovery mechanism for agents.
    ///         Agents call eth_getLogs filtering by puzzleId to get all clues.
    event ClueDeposited(
        bytes32 indexed puzzleId,
        uint256 index,
        uint8   clueType,
        bytes   data        // ABI-encoded clue payload
    );

    event PuzzleStatusChanged(bytes32 indexed puzzleId, bool active);

    // ─── Modifiers ────────────────────────────────────────────────────────────
    modifier onlyOwner() {
        require(msg.sender == owner, "PuzzleRegistry: not owner");
        _;
    }

    modifier puzzleExists(bytes32 puzzleId) {
        require(puzzles[puzzleId].verifier != address(0), "PuzzleRegistry: unknown puzzle");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    // ─── Admin ────────────────────────────────────────────────────────────────

    /// @notice Register a new puzzle with its EZKL verifier.
    function createPuzzle(
        bytes32 puzzleId,
        address verifier,
        string  calldata metadataURI
    ) external onlyOwner {
        require(puzzles[puzzleId].verifier == address(0), "PuzzleRegistry: already exists");
        require(verifier != address(0), "PuzzleRegistry: zero verifier");

        puzzles[puzzleId] = Puzzle({
            verifier:    verifier,
            clueCount:   0,
            active:      true,
            metadataURI: metadataURI
        });
        puzzleIds.push(puzzleId);

        emit PuzzleCreated(puzzleId, verifier, metadataURI);
    }

    /// @notice Add a clue to an existing puzzle.
    ///         Agents discover clues via ClueDeposited events.
    function depositClue(
        bytes32 puzzleId,
        uint8   clueType,
        bytes   calldata data
    ) external onlyOwner puzzleExists(puzzleId) {
        uint256 idx = puzzles[puzzleId].clueCount;
        puzzles[puzzleId].clueCount = idx + 1;
        emit ClueDeposited(puzzleId, idx, clueType, data);
    }

    /// @notice Convenience: deposit multiple clues in one tx.
    function depositClues(
        bytes32    puzzleId,
        uint8[]    calldata clueTypes,
        bytes[]    calldata dataArr
    ) external onlyOwner puzzleExists(puzzleId) {
        require(clueTypes.length == dataArr.length, "PuzzleRegistry: length mismatch");
        uint256 idx = puzzles[puzzleId].clueCount;
        for (uint256 i = 0; i < clueTypes.length; i++) {
            emit ClueDeposited(puzzleId, idx + i, clueTypes[i], dataArr[i]);
        }
        puzzles[puzzleId].clueCount = idx + clueTypes.length;
    }

    function setPuzzleActive(bytes32 puzzleId, bool active)
        external onlyOwner puzzleExists(puzzleId)
    {
        puzzles[puzzleId].active = active;
        emit PuzzleStatusChanged(puzzleId, active);
    }

    // ─── Views ────────────────────────────────────────────────────────────────

    function getVerifier(bytes32 puzzleId) external view returns (address) {
        return puzzles[puzzleId].verifier;
    }

    function isPuzzleActive(bytes32 puzzleId) external view returns (bool) {
        return puzzles[puzzleId].active;
    }

    function getPuzzleCount() external view returns (uint256) {
        return puzzleIds.length;
    }

    /// @notice Explicit struct getter — used by ZkMLNFT and external callers.
    ///         Public mapping auto-getter can't reliably return structs with
    ///         dynamic fields (string) across contract boundaries.
    function getPuzzle(bytes32 puzzleId)
        external view
        returns (Puzzle memory)
    {
        return puzzles[puzzleId];
    }
}
