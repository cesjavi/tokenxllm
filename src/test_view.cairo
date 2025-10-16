// src/test_view.cairo
#[starknet::contract]
mod t {
    #[storage] struct Storage {}
    #[view] fn ping(self: @ContractState) -> felt252 { 'ok' }
}

