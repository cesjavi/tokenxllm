// Interfaz mínima ERC-20 remota (dispatcher)
#[starknet::interface]
trait IRemoteERC20<TContractState> {
    fn transfer_from(ref self: TContractState, from: ContractAddress, to: ContractAddress, value: u256);
    fn decimals(self: @TContractState) -> u8;
}
use IRemoteERC20DispatcherTrait;
