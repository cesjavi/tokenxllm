// src/contracts/erc20/AIC.cairo
use core::traits::TryInto;
use starknet::ContractAddress;
use starknet::storage::Map;

// =======================
// Interfaz ERC-20 (ABI pública)
// =======================
#[starknet::interface]
trait IAIC<TContractState> {
    // Lecturas
    fn name(self: @TContractState) -> felt252;
    fn symbol(self: @TContractState) -> felt252;
    fn decimals(self: @TContractState) -> u8;
    fn total_supply(self: @TContractState) -> u256;
    fn balance_of(self: @TContractState, account: ContractAddress) -> u256;
    fn allowance(self: @TContractState, owner: ContractAddress, spender: ContractAddress) -> u256;
    fn owner(self: @TContractState) -> ContractAddress;

    // Aliases camelCase (compat wallets/tools)
    fn balanceOf(self: @TContractState, account: felt252) -> u256;
    fn totalSupply(self: @TContractState) -> u256;

    // Mutaciones
    fn transfer(ref self: TContractState, to: ContractAddress, value: u256);
    fn approve(ref self: TContractState, spender: ContractAddress, value: u256);
    fn transfer_from(ref self: TContractState, from: ContractAddress, to: ContractAddress, value: u256);

    // Mint administrado (entrypoint expuesto)
    fn owner_mint(ref self: TContractState, to: ContractAddress, value: u256);
}

// =======================
// Contrato
// =======================
#[starknet::contract]
mod AIC {
    use super::{IAIC, ContractAddress, TryInto, Map};
    use starknet::get_caller_address;
    use starknet::storage::{
        StorageMapReadAccess,
        StorageMapWriteAccess,
        StoragePointerReadAccess,   // habilita .read() en campos simples
        StoragePointerWriteAccess,  // habilita .write() en campos simples
    };

    // =======================
    // Eventos
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
    // ABI pública (embed_v0)
    // =======================
    #[abi(embed_v0)]
    impl AICImpl of super::IAIC<ContractState> {
        // ----- Lecturas -----
        fn name(self: @ContractState) -> felt252 { self.name.read() }
        fn symbol(self: @ContractState) -> felt252 { self.symbol.read() }
        fn decimals(self: @ContractState) -> u8 { self.decimals.read() }
        fn total_supply(self: @ContractState) -> u256 { self.total_supply.read() }
        fn owner(self: @ContractState) -> ContractAddress { self.owner.read() }

        fn balance_of(self: @ContractState, account: ContractAddress) -> u256 {
            self.balances.read(account)
        }

        fn allowance(
            self: @ContractState,
            owner: ContractAddress,
            spender: ContractAddress
        ) -> u256 {
            self.allowances.read((owner, spender))
        }

        // Aliases camelCase
        fn balanceOf(self: @ContractState, account: felt252) -> u256 {
            // convierte felt -> ContractAddress
            let addr: ContractAddress = account.try_into().unwrap();
            self.balances.read(addr)
        }
        fn totalSupply(self: @ContractState) -> u256 {
            self.total_supply.read()
        }

        // ----- Mutaciones -----
        fn transfer(ref self: ContractState, to: ContractAddress, value: u256) {
            let sender = get_caller_address();
            _transfer(ref self, sender, to, value);
            self.emit(Event::Transfer(Transfer { from: sender, to, value }));
        }

        fn approve(ref self: ContractState, spender: ContractAddress, value: u256) {
            let owner = get_caller_address();
            self.allowances.write((owner, spender), value);
            self.emit(Event::Approval(Approval { owner, spender, value }));
        }

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

        // ----- Mint admin -----
        fn owner_mint(ref self: ContractState, to: ContractAddress, value: u256) {
            assert_only_owner(@self);

            // Actualizar supply
            let supply = self.total_supply.read();
            self.total_supply.write(supply + value);

            // Actualizar balance
            let to_bal = self.balances.read(to);
            self.balances.write(to, to_bal + value);

            // Emite Transfer desde la zero address (compat ERC-20)
            let zero: ContractAddress = 0.try_into().unwrap();
            self.emit(Event::Transfer(Transfer { from: zero, to, value }));
        }
    }

    // =======================
    // Internos
    // =======================
    fn _transfer(ref self: ContractState, from: ContractAddress, to: ContractAddress, value: u256) {
        let from_bal = self.balances.read(from);
        assert(from_bal >= value, 'BALANCE');

        self.balances.write(from, from_bal - value);
        let to_bal = self.balances.read(to);
        self.balances.write(to, to_bal + value);
    }

    fn assert_only_owner(self: @ContractState) {
        let caller = get_caller_address();
        let current_owner = self.owner.read();
        assert(caller == current_owner, 'OWNER');
    }
}
