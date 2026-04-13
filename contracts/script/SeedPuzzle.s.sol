// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {PuzzleRegistry} from "../src/PuzzleRegistry.sol";

/// @notice Seeds puzzle_001 on-chain with free clues.
///         Run after deploying the verifier and registry.
///
///   forge script script/SeedPuzzle.s.sol \
///     --rpc-url abstract_testnet --broadcast
contract SeedPuzzle is Script {
    bytes32 constant PUZZLE_001 =
        0x0000000000000000000000000000000000000000000000000000000000000001;

    function run() external {
        address registryAddr = vm.envAddress("PUZZLE_REGISTRY_ADDRESS");
        address verifierAddr = vm.envAddress("HALO2_VERIFIER_ADDRESS");
        uint256 deployerKey  = vm.envUint("PRIVATE_KEY");

        PuzzleRegistry registry = PuzzleRegistry(registryAddr);

        vm.startBroadcast(deployerKey);

        // Register puzzle
        registry.createPuzzle(
            PUZZLE_001,
            verifierAddr,
            "https://agentoyunu.com/metadata/puzzle_001/"
        );
        console.log("Puzzle created");

        // Free on-chain clues (agents discover via eth_getLogs)
        // IMPORTANT: Clues must NOT contain the answer — they should guide
        // the agent toward it through description, hints, and elimination.
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

        registry.depositClues(PUZZLE_001, types, data);
        console.log("2 free clues deposited");

        // TYPE_POINTER clue → directs agent to x402 server for paid clues
        // NOTE: Uncomment when x402 server is deployed and active.
        // registry.depositClue(
        //     PUZZLE_001,
        //     4, // TYPE_POINTER
        //     abi.encode(
        //         "x402",                                // protocol
        //         "https://agentoyunu.com/ipucu/puzzle_001", // base URL
        //         uint256(3),                            // number of paid clues
        //         uint256(1e6)                           // price per clue (1 USDC, 6 decimals)
        //     )
        // );
        // console.log("x402 pointer clue deposited");

        vm.stopBroadcast();
    }
}
