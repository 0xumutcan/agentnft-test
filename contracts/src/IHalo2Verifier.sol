// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Interface for EZKL-generated Halo2 verifier contracts.
interface IHalo2Verifier {
    function verifyProof(
        bytes calldata proof,
        uint256[] calldata instances
    ) external view returns (bool);
}
