#[starknet::contract]
mod AIC {
    use starknet::{ContractAddress, get_caller_address};
    use starknet::storage::{
        Map,
        StorageMapReadAccess, StorageMapWriteAccess,
        StoragePointerReadAccess, StoragePointerWriteAccess,
    };

    #[storage]
    struct Storage {
        name: felt252,
        symbol: felt252,
        decimals: u8,
        total_supply: u256,
        balances: Map<ContractAddress, u256>,
        allowances: Map<(ContractAddress, ContractAddress), u256>,
        owner: ContractAddress,
    }

    // --- Constructor ---
    #[constructor]
    fn constructor(
        ref self: ContractState,
        name: felt252, symbol: felt252, decimals: u8, owner: ContractAddress
    ) {
        self.name.write(name);
        self.symbol.write(symbol);
        self.decimals.write(decimals);
        self.owner.write(owner);
        self.total_supply.write(0_u256);
    }

    // --- Lecturas (externals v0 para compatibilidad del plugin) ---
    #[external(v0)]
    fn name(ref self: ContractState) -> felt252 { self.name.read() }

    #[external(v0)]
    fn symbol(ref self: ContractState) -> felt252 { self.symbol.read() }

    #[external(v0)]
    fn decimals(ref self: ContractState) -> u8 { self.decimals.read() }

    #[external(v0)]
    fn total_supply(ref self: ContractState) -> u256 { self.total_supply.read() }

    #[external(v0)]
    fn balance_of(ref self: ContractState, account: ContractAddress) -> u256 {
        self.balances.read(account)
    }

    #[external(v0)]
    fn allowance(ref self: ContractState, owner: ContractAddress, spender: ContractAddress) -> u256 {
        self.allowances.read((owner, spender))
    }

    // --- Mutaciones ---
    #[external(v0)]
    fn transfer(ref self: ContractState, to: ContractAddress, value: u256) {
        let sender = get_caller_address();
        _transfer(ref self, sender, to, value);
    }

    #[external(v0)]
    fn approve(ref self: ContractState, spender: ContractAddress, value: u256) {
        let sender = get_caller_address();
        self.allowances.write((sender, spender), value);
    }

    #[external(v0)]
    fn transfer_from(
        ref self: ContractState, from: ContractAddress, to: ContractAddress, value: u256
    ) {
        let caller = get_caller_address();
        let allowed = self.allowances.read((from, caller));
        assert(allowed >= value, 'ALLOWANCE');
        self.allowances.write((from, caller), allowed - value);
        _transfer(ref self, from, to, value);
    }

    #[external(v0)]
    fn mint(ref self: ContractState, to: ContractAddress, value: u256) {
        let caller = get_caller_address();
        assert(caller == self.owner.read(), 'OWNER');
        let supply = self.total_supply.read();
        self.total_supply.write(supply + value);
        let to_bal = self.balances.read(to);
        self.balances.write(to, to_bal + value);
    }

    // --- Interno ---
    fn _transfer(ref self: ContractState, from: ContractAddress, to: ContractAddress, value: u256) {
        let from_bal = self.balances.read(from);
        assert(from_bal >= value, 'BALANCE');
        self.balances.write(from, from_bal - value);
        let to_bal = self.balances.read(to);
        self.balances.write(to, to_bal + value);
    }
}
