#[starknet::contract]
mod UsageManager {
    use starknet::ContractAddress;
    use starknet::{get_caller_address, get_block_timestamp};
    use starknet::storage::{
        Map,
        StorageMapReadAccess,
        StorageMapWriteAccess,
        StoragePointerReadAccess,
        StoragePointerWriteAccess,
    };

    // ---- Interfaz ERC-20 remota, aislada en submódulo para evitar colisiones ----
    mod erc20_iface {
        use super::ContractAddress;

        #[starknet::interface]
        pub trait ERC20ForUM<TContractState> {
            fn transfer_from(
                ref self: TContractState,
                from: ContractAddress,
                to: ContractAddress,
                value: u256
            );
            fn decimals(self: @TContractState) -> u8;
        }
    }

    // Use the dispatcher and trait directly from the module
    use erc20_iface::ERC20ForUMDispatcher;
    use erc20_iface::ERC20ForUMDispatcherTrait;

    #[storage]
    struct Storage {
        token: ContractAddress,
        treasury: ContractAddress,
        free_quota_per_epoch: u64,
        price_per_unit_wei: u256,
        epoch_seconds: u64,
        admin: ContractAddress,
        user_used_in_epoch: Map<(ContractAddress, u64), u64>,
    }

    #[constructor]
    fn constructor(
        ref self: ContractState,
        token: ContractAddress,
        treasury: ContractAddress,
        free_quota_per_epoch: u64,
        price_per_unit_wei: u256,
        epoch_seconds: u64,
        admin: ContractAddress
    ) {
        self.token.write(token);
        self.treasury.write(treasury);
        self.free_quota_per_epoch.write(free_quota_per_epoch);
        self.price_per_unit_wei.write(price_per_unit_wei);
        self.epoch_seconds.write(epoch_seconds);
        self.admin.write(admin);
    }

    // ------- Lecturas (externals v0 para compat. del plugin) -------
    #[external(v0)]
    fn get_epoch_id(ref self: ContractState) -> u64 {
        let ts: u64 = get_block_timestamp();
        ts / self.epoch_seconds.read()
    }

    #[external(v0)]
    fn used_in_current_epoch(ref self: ContractState, user: ContractAddress) -> u64 {
        let ts: u64 = get_block_timestamp();
        let eid: u64 = ts / self.epoch_seconds.read();
        self.user_used_in_epoch.read((user, eid))
    }

    // ------- Lógica principal -------
    #[external(v0)]
    fn authorize_usage(ref self: ContractState, units: u64) {
        let caller = get_caller_address();
        let ts: u64 = get_block_timestamp();
        let eid: u64 = ts / self.epoch_seconds.read();

        let used = self.user_used_in_epoch.read((caller, eid));
        let free_quota = self.free_quota_per_epoch.read();

        let new_used: u64 = used + units;
        let free_remaining: u64 = if used >= free_quota { 0_u64 } else { free_quota - used };
        let paid_units: u64 = if units <= free_remaining { 0_u64 } else { units - free_remaining };

        if paid_units > 0_u64 {
            let price: u256 = self.price_per_unit_wei.read();

            // u64 -> u256 sin traits externos
            let paid_low: u128 = paid_units.into();
            let paid_256: u256 = u256 { low: paid_low, high: 0_u128 };

            let total_cost: u256 = price * paid_256;

            let token_addr = self.token.read();
            let erc20 = ERC20ForUMDispatcher { contract_address: token_addr };
            erc20.transfer_from(caller, self.treasury.read(), total_cost);
        }

        self.user_used_in_epoch.write((caller, eid), new_used);
    }

    // ------- Administración -------
    #[external(v0)]
    fn set_price_per_unit_wei(ref self: ContractState, new_price: u256) {
        assert(get_caller_address() == self.admin.read(), 'ADMIN');
        self.price_per_unit_wei.write(new_price);
    }

    #[external(v0)]
    fn set_free_quota_per_epoch(ref self: ContractState, new_quota: u64) {
        assert(get_caller_address() == self.admin.read(), 'ADMIN');
        self.free_quota_per_epoch.write(new_quota);
    }
}