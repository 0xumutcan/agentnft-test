// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {PuzzleRegistry} from "../src/PuzzleRegistry.sol";

/// @notice Deactivates puzzle_001 (bad clues) and creates puzzle_002
///         with correct clues that do NOT reveal the answer.
///
///   forge script script/ReseedPuzzle.s.sol \
///     --rpc-url abstract_testnet --broadcast
contract ReseedPuzzle is Script {
    bytes32 constant PUZZLE_001 =
        0x0000000000000000000000000000000000000000000000000000000000000001;
    bytes32 constant PUZZLE_002 =
        0x0000000000000000000000000000000000000000000000000000000000000002;

    function run() external {
        address registryAddr = vm.envAddress("PUZZLE_REGISTRY_ADDRESS");
        address verifierAddr = vm.envAddress("HALO2_VERIFIER_ADDRESS");
        uint256 deployerKey  = vm.envUint("PRIVATE_KEY");

        PuzzleRegistry registry = PuzzleRegistry(registryAddr);

        vm.startBroadcast(deployerKey);

        // ── 1. Deactivate old puzzle (clues leaked the answer) ───────────────
        registry.setPuzzleActive(PUZZLE_001, false);
        console.log("Puzzle 001 deactivated");

        // ── 2. Create new puzzle with same verifier ──────────────────────────
        registry.createPuzzle(
            PUZZLE_002,
            verifierAddr,
            "https://agentoyunu.com/metadata/puzzle_002/"
        );
        console.log("Puzzle 002 created");

        // ── 3. Deposit clues — descriptive but do NOT contain the answer ─────
        uint8[] memory types = new uint8[](2);
        types[0] = registry.TYPE_TEXT();
        types[1] = registry.TYPE_HINT();

        bytes[] memory data = new bytes[](2);
        data[0] = abi.encode(
            "Guney yarimkurenin en zarif smokin sahibi, soguga meydan okuyan varlik."
        );
        data[1] = abi.encode(
            "Hayvanlar alemi. Denizde yuzer, karada yurur. Asla ucmaz."
        );

        registry.depositClues(PUZZLE_002, types, data);
        console.log("2 free clues deposited (no answer leak, no pointer)");

        vm.stopBroadcast();
    }
}
