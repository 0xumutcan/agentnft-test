// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Strings} from "@openzeppelin/contracts/utils/Strings.sol";
import {PuzzleRegistry} from "./PuzzleRegistry.sol";
import {IHalo2Verifier} from "./IHalo2Verifier.sol";

/// @title ZkMLNFT
/// @notice ERC-721 NFT gated by zkML proof.
///         Minting requires a valid EZKL Halo2 proof that the submitted
///         answer embedding passes the per-puzzle MLP validator.
contract ZkMLNFT is ERC721, Ownable {
    using Strings for uint256;
    PuzzleRegistry public immutable registry;

    uint256 private _nextTokenId;

    // puzzle => solver => claimed
    mapping(bytes32 => mapping(address => bool)) public claimed;

    // tokenId => puzzleId  (for metadata routing)
    mapping(uint256 => bytes32) public tokenPuzzle;

    event PuzzleSolved(
        bytes32 indexed puzzleId,
        address indexed solver,
        uint256 tokenId
    );

    constructor(address _registry)
        ERC721("zkML Puzzle NFT", "ZKPUZ")
        Ownable(msg.sender)
    {
        registry = PuzzleRegistry(_registry);
    }

    // ─── Mint ─────────────────────────────────────────────────────────────────

    /// @notice Mint an NFT by submitting a valid zkML proof.
    /// @param puzzleId     The puzzle being solved.
    /// @param proof        Halo2 proof bytes (output of `ezkl prove`).
    /// @param instances    Public inputs: flattened field elements
    ///                     (embedding values + MLP output score).
    function mintWithProof(
        bytes32        puzzleId,
        bytes calldata proof,
        uint256[] calldata instances
    ) external {
        require(registry.isPuzzleActive(puzzleId), "ZkMLNFT: puzzle inactive");
        require(!claimed[puzzleId][msg.sender],     "ZkMLNFT: already claimed");

        address verifier = registry.getVerifier(puzzleId);
        require(verifier != address(0), "ZkMLNFT: no verifier");

        // ── Core check: EZKL Halo2 proof verification ────────────────────────
        // The verifier was compiled with threshold=0.7 baked in as a constraint.
        // If the MLP output < 0.7 the proof cannot be constructed at all.
        require(
            IHalo2Verifier(verifier).verifyProof(proof, instances),
            "ZkMLNFT: invalid zkML proof"
        );

        claimed[puzzleId][msg.sender] = true;

        uint256 tokenId = _nextTokenId++;
        tokenPuzzle[tokenId] = puzzleId;
        _safeMint(msg.sender, tokenId);

        emit PuzzleSolved(puzzleId, msg.sender, tokenId);
    }

    // ─── Metadata ─────────────────────────────────────────────────────────────

    function tokenURI(uint256 tokenId)
        public view override returns (string memory)
    {
        _requireOwned(tokenId);
        bytes32 puzzleId  = tokenPuzzle[tokenId];
        // Use explicit getPuzzle() — avoids cross-contract struct tuple ambiguity
        PuzzleRegistry.Puzzle memory p = registry.getPuzzle(puzzleId);
        return string(abi.encodePacked(p.metadataURI, tokenId.toString()));
    }
}
