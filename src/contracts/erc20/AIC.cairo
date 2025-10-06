#[starknet::contract]
mod tokenxllm {
    use starknet::{ContractAddress, get_caller_address};
    use starknet::storage::{
        Map,
        StorageMapReadAccess, StorageMapWriteAccess,
        StoragePointerReadAccess, StoragePointerWriteAccess,
    };
    use core::traits::TryInto; // <- ruta correcta en Cairo 2.x

    // =======================
    // Events (Cairo 2.6.x)
    // =======================
    #[derive(starknet::Event, Drop)]
    #[event]
    enum Event {
        Transfer: Transfer,
        Approval: Approval,
    }

    #[derive(Copy, Drop, Serde, starknet::Event)]
    struct Transfer {
        #[key] from: ContractAddress,
        #[key] to:   ContractAddress,
        value: u256,
    }

    #[derive(Copy, Drop, Serde, starknet::Event)]
    struct Approval {
        #[key] owner:   ContractAddress,
        #[key] spender: ContractAddress,
        value: u256,
    }

    // =======================
    // Storage
    // =======================
    #[storage]
    struct Storage {
        // Metadata
        name: felt252,
        symbol: felt252,
        decimals: u8,

        // ERC-20 core
        total_supply: u256,
        balances: Map<ContractAddress, u256>,
        allowances: Map<(ContractAddress, ContractAddress), u256>,

        // Admin
        owner: ContractAddress,
    }

    // =======================
    // Constructor
    // =======================
    #[constructor]
    fn constructor(
        ref self: ContractState,
        name: felt252,
        symbol: felt252,
        decimals: u8,
        owner: ContractAddress
    ) {
        self.name.write(name);
        self.symbol.write(symbol);
        self.decimals.write(decimals);
        self.owner.write(owner);
        self.total_supply.write(0_u256);
    }

    // =======================
    // Helpers
    // =======================
    fn zero_address() -> ContractAddress {
        0.try_into().unwrap()
    }

    // =======================
    // Lecturas (externals v0)
    // =======================
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

    // Aliases camelCase (compat)
    #[external(v0)]
    fn balanceOf(ref self: ContractState, account: ContractAddress) -> u256 {
        self.balances.read(account)
    }

    #[external(v0)]
    fn totalSupply(ref self: ContractState) -> u256 {
        self.total_supply.read()
    }

    #[external(v0)]
    fn allowance(
        ref self: ContractState,
        owner: ContractAddress,
        spender: ContractAddress
    ) -> u256 {
        self.allowances.read((owner, spender))
    }

    // =======================
    // Mutaciones (externals v0)
    // =======================
    #[external(v0)]
    fn transfer(ref self: ContractState, to: ContractAddress, value: u256) {
        let sender = get_caller_address();
        _transfer(ref self, sender, to, value);
        self.emit(Event::Transfer(Transfer { from: sender, to, value }));
    }

    #[external(v0)]
    fn approve(ref self: ContractState, spender: ContractAddress, value: u256) {
        let owner = get_caller_address();
        self.allowances.write((owner, spender), value);
        self.emit(Event::Approval(Approval { owner, spender, value }));
    }

    #[external(v0)]
    fn transfer_from(
        ref self: ContractState,
        from: ContractAddress,
        to: ContractAddress,
        value: u256
    ) {
        let caller = get_caller_address();
        let allowed = self.allowances.read((from, caller));
        assert(allowed >= value, 'ALLOWANCE');

        self.allowances.write((from, caller), allowed - value);
        _transfer(ref self, from, to, value);

        self.emit(Event::Transfer(Transfer { from, to, value }));
    }

    #[external(v0)]
    fn mint(ref self: ContractState, to: ContractAddress, value: u256) {
        let caller = get_caller_address();
        assert(caller == self.owner.read(), 'OWNER');

        let supply = self.total_supply.read();
        self.total_supply.write(supply + value);

        let to_bal = self.balances.read(to);
        self.balances.write(to, to_bal + value);

        // ERC-20: emite Transfer desde la "zero address"
        let zero = zero_address();
        self.emit(Event::Transfer(Transfer { from: zero, to, value }));
    }

    // =======================
    // Internos
    // =======================
    fn _transfer(
        ref self: ContractState,
        from: ContractAddress,
        to: ContractAddress,
        value: u256
    ) {
        let from_bal = self.balances.read(from);
        assert(from_bal >= value, 'BALANCE');

        self.balances.write(from, from_bal - value);

        let to_bal = self.balances.read(to);
        self.balances.write(to, to_bal + value);
    }
}
