from typing import cast, Optional
from pathlib import Path
from pyheck import upper_camel
from genpy import (
    Import,
    FromImport,
    Assign,
    Suite,
    Collection,
    ImportAs,
    Return,
)
from anchorpy.coder.common import _sighash
from anchorpy.idl import (
    Idl,
    _IdlAccounts,
    _IdlAccountItem,
)
from anchorpy.clientgen.utils import (
    TypedParam,
    TypedDict,
    StrDict,
    StrDictEntry,
    List,
    Function,
)
from anchorpy.clientgen.common import (
    _py_type_from_idl,
    _layout_for_type,
    _field_to_encodable,
)


def gen_instructions(idl: Idl, root: Path) -> None:
    instructions_dir = root / "instructions"
    instructions_dir.mkdir(exist_ok=True)
    gen_index_file(idl, instructions_dir)
    instructions = gen_instructions_code(idl, instructions_dir)
    for path, code in instructions.items():
        path.write_text(code)


def gen_index_file(idl: Idl, instructions_dir: Path) -> None:
    code = gen_index_code(idl)
    path = instructions_dir / "__init__.py"
    path.write_text(code)


def gen_index_code(idl: Idl) -> str:
    imports: list[FromImport] = []
    for ix in idl.instructions:
        import_members: list[str] = []
        if ix.args:
            import_members.append(_args_interface_name(ix.name))
        if ix.accounts:
            import_members.append(_accounts_interface_name(ix.name))
        imports.append(FromImport(f".{ix.name}", import_members))
    return str(Collection(imports))


def _args_interface_name(ix_name: str) -> str:
    return f"{upper_camel(ix_name)}Args"


def _accounts_interface_name(ix_name: str) -> str:
    return f"{upper_camel(ix_name)}Accounts"


def recurse_accounts(accs: list[_IdlAccountItem], nested_names: list[str]) -> list[str]:
    elements: list[str] = []
    for acc in accs:
        names = [*nested_names, acc.name]
        if isinstance(acc, _IdlAccounts):
            nested_accs = cast(_IdlAccounts, acc)
            elements.extend(recurse_accounts(nested_accs.accounts, names))
        else:
            nested_keys = [f'["{key}"]' for key in names]
            dict_accessor = "".join(nested_keys)
            elements.append(
                f"AccountMeta(pubkey=accounts{dict_accessor}, "
                f"is_signer={acc.is_signer}, "
                f"is_writable={acc.is_mut})"
            )
    return elements


def gen_accounts(
    name,
    idl_accs: list[_IdlAccountItem],
    extra_typeddicts: Optional[list[TypedDict]] = None,
) -> list[TypedDict]:
    extra_typeddicts_to_use = [] if extra_typeddicts is None else extra_typeddicts
    params: list[TypedParam] = []
    for acc in idl_accs:
        if isinstance(acc, _IdlAccounts):
            nested_accs = cast(_IdlAccounts, acc)
            nested_acc_name = f"{upper_camel(nested_accs.name)}Nested"
            params.append(TypedParam(acc.name, nested_acc_name))
            extra_typeddicts_to_use = extra_typeddicts_to_use + (
                gen_accounts(
                    nested_acc_name,
                    nested_accs.accounts,
                    extra_typeddicts_to_use,
                )
            )
        else:
            params.append(TypedParam(acc.name, "PublicKey"))
    return [TypedDict(name, params)] + extra_typeddicts_to_use


def gen_instructions_code(idl: Idl, out: Path) -> dict[Path, str]:
    types_import = [FromImport("..", ["types"])] if idl.types else []
    imports = [
        Import("typing"),
        FromImport("solana.publickey", ["PublicKey"]),
        FromImport("solana.transaction", ["TransactionInstruction", "AccountMeta"]),
        ImportAs("borsh_construct", "borsh"),
        *types_import,
        FromImport("..program_id", ["PROGRAM_ID"]),
    ]
    result = {}
    for ix in idl.instructions:
        filename = (out / ix.name).with_suffix(".py")
        args_interface_params: list[TypedParam] = []
        layout_items: list[str] = []
        encoded_args_entries: list[StrDictEntry] = []
        accounts_interface_name = _accounts_interface_name(ix.name)
        for arg in ix.args:
            args_interface_params.append(
                TypedParam(arg.name, _py_type_from_idl(idl, arg.type))
            )
            layout_items.append(_layout_for_type(arg.type, arg.name))
            encoded_args_entries.append(
                StrDictEntry(
                    arg.name, _field_to_encodable(idl, arg, 'args["', val_suffix='"]')
                )
            )
        if ix.args:
            args_interface_name = _args_interface_name(ix.name)
            args_interface_container = [
                TypedDict(args_interface_name, args_interface_params)
            ]
            layout_assignment_container = [
                Assign("layout", f"borsh.CStruct({','.join(layout_items)})")
            ]
            args_container = [TypedParam("args", args_interface_name)]
            accounts_container = [TypedParam("accounts", accounts_interface_name)]
        else:
            args_interface_container = []
            layout_assignment_container = []
            args_container = []
            accounts_container = []
        accounts = gen_accounts(accounts_interface_name, ix.accounts)
        keys_assignment = Assign("keys", List(recurse_accounts(ix.accounts, [])))
        identifier_assignment = Assign("identifier", _sighash(ix.name))
        encoded_args_assignment = Assign(
            "encoded_args", f"layout.build({StrDict(encoded_args_entries)})"
        )
        data_assignment = Assign("data", "identifier + encoded_args")
        returning = Return("TransactionInstruction(data, keys, PROGRAM_ID)")
        ix_fn = Function(
            ix.name,
            [*args_container, *accounts_container],
            Suite(
                [
                    keys_assignment,
                    identifier_assignment,
                    encoded_args_assignment,
                    data_assignment,
                    returning,
                ]
            ),
            "TransactionInstruction",
        )
        contents = Collection(
            [
                *imports,
                *args_interface_container,
                *layout_assignment_container,
                *accounts,
                ix_fn,
            ]
        )
        result[filename] = str(contents)
    return result