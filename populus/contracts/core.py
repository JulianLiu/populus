import copy
import hashlib
import itertools

from ethereum import utils as ethereum_utils

from populus.contracts.functions import Function
from populus.contracts.events import Event


class ContractBase(object):
    def __init__(self, address, rpc_client):
        functions = {fn.name: fn for fn in (copy.copy(f) for f in self._config._functions)}
        events = {ev.name: ev for ev in (copy.copy(e) for e in self._config._events)}
        for obj in itertools.chain(functions.values(), events.values()):
            obj._bind(self)
        self._meta = ContractMeta(address, rpc_client, functions, events)

    def __str__(self):
        return "{name}({address})".format(name=self.__class__.__name__, address=self.address)

    @classmethod
    def get_deploy_data(cls, *args):
        data = cls._config.code
        if args:
            if cls._config.constructor is None:
                raise ValueError("This contract does not appear to have a constructor")
            data += ethereum_utils.encode_hex(cls._config.constructor.abi_args_signature(args))

        return data

    #
    #  Instance Methods
    #
    def get_balance(self, block="latest"):
        return self._meta.rpc_client.get_balance(self._meta.address, block=block)


class ContractMeta(object):
    """
    Instance level contract data.
    """
    def __init__(self, address, rpc_client, functions, events):
        self.address = address
        self.rpc_client = rpc_client
        self.functions = functions
        self.events = events


class Config(object):
    """
    Contract (class) level contract data.
    """
    def __init__(self, code, source, abi, functions, events, constructor):
        self.code = code
        self.source = source
        self.abi = abi
        self._functions = functions
        self._events = events
        self.constructor = constructor


def Contract(contract_meta, contract_name=None):
    _abi = contract_meta['info']['abiDefinition']
    code = contract_meta['code']
    source = contract_meta['info']['source']

    if contract_name is None:
        contract_name = "Unknown-{0}".format(hashlib.md5(code).hexdigest())

    functions = []
    events = []
    constructor = None

    _dict = {}

    for signature_item in _abi:
        if signature_item['type'] == 'constructor':
            # Constructors don't need to be part of a contract's methods
            if signature_item.get('inputs'):
                constructor = Function(
                    name='constructor',
                    inputs=signature_item['inputs'],
                )
            continue

        if signature_item['name'] in _dict:
            # TODO: handle namespace conflicts
            raise ValueError("About to overwrite a function signature for duplicate function name {0}".format(signature_item['name']))  # NOQA

        if signature_item['type'] == 'function':
            # make sure we're not overwriting a signature

            func = Function(
                name=signature_item['name'],
                inputs=signature_item['inputs'],
                outputs=signature_item['outputs'],
                constant=signature_item['constant'],
            )
            _dict[signature_item['name']] = func
            functions.append(func)
        elif signature_item['type'] == 'event':
            event = Event(
                name=signature_item['name'],
                inputs=signature_item['inputs'],
                anonymous=signature_item['anonymous'],
            )
            _dict[signature_item['name']] = event
            events.append(event)
        else:
            raise ValueError("Unknown signature item '{0}'".format(signature_item))

    docstring = """
    contract {contract_name} {{
    // Events
    {events}

    // Functions
    {functions}
    }}
    """.format(
        contract_name=contract_name,
        functions='\n'.join(str(f) for f in functions),
        events='\n'.join(str(e) for e in events),
    )

    _dict['__doc__'] = docstring
    _dict['_config'] = Config(code, source, _abi, functions, events, constructor)

    return type(str(contract_name), (ContractBase,), _dict)
