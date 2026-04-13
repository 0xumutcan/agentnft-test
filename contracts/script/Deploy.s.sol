// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {PuzzleRegistry} from "../src/PuzzleRegistry.sol";
import {ZkMLNFT} from "../src/ZkMLNFT.sol";

contract Deploy is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        vm.startBroadcast(deployerKey);

        PuzzleRegistry registry = new PuzzleRegistry();
        console.log("PuzzleRegistry:", address(registry));

        ZkMLNFT nft = new ZkMLNFT(address(registry));
        console.log("ZkMLNFT:", address(nft));

        vm.stopBroadcast();
    }
}
