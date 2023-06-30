#!/usr/bin/env python3

# tinyssb/keystore.py
# 2022-04-09 <christian.tschudin@unibas.ch>
from collections import OrderedDict

import bipf
import pure25519
from . import util

# from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey, Ed25519PrivateKey
# from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey, X25519PrivateKey

# from cryptography.hazmat.backends import default_backend
# from cryptography.hazmat.primitives import serialization
# from cryptography.hazmat.primitives.asymmetric import dh


# ----------------------------------------------------------------------

class Keystore:

    def __init__(self, cfg=None):
        if cfg is None:
            cfg = {}  # default arguments are evaluated only once, behaves as a global var
        self.kv = OrderedDict()
        for pk,d in cfg.items():
            self.kv[util.fromhex(pk)] = [util.fromhex(d['sk']), d['name']]

    def dump(self, fn):
        # write DB to BIPF file
        data = bipf.dumps(dict(self.kv))
        with util.atomic_write(fn, binary=True) as f:
            f.write(data)

    def load(self, fn):
        # read DB from BIPF file
        with open(fn, 'rb') as f:
            data = f.read()
        self.kv = bipf.loads(data)

    def new(self, nm=None):
        """
        Add a new feedID to the keystore without deleting others.

        The new key pair is unrelated to the other IDs.
        """
        sk, _ = pure25519.create_keypair()
        sk,pk = sk.sk_s[:32], sk.vk_s # just the bytes
        self.add(pk, sk, nm)
        return pk

    def add(self, pk, sk=None, nm=None):
        self.kv[pk] = [sk,nm]

    def remove(self, pk):
        del self.kv[pk]

    def sign(self, pk, msg):
        sk = pure25519.SigningKey(self.kv[pk][0])
        return sk.sign(msg)

    def get_signFct(self, pk):
        return mksignfct(self.kv[pk][0])

    def verify(self, pk, sig, msg):
        try:
            pure25519.VerifyingKey(pk).verify(sig,msg)
            return True
        except Exception as e:
            print(e)
            pass
        return False

    def __str__(self):
        out = OrderedDict()
        for pk,(sk,nm) in self.kv.items():
            out[util.hex(pk)] = { 'sk': util.hex(sk), 'name': nm }
        return util.json_pp(out)
        
def mksignfct(secret):
    def sign(m):
        sk = pure25519.SigningKey(secret)
        return sk.sign(m)
    return sign

def mkverifyfct(secret):
    def vfct(pk, s, msg):
        try:
            pure25519.VerifyingKey(pk).verify(s,msg)
            return True
        except Exception as e:
            print(e)
            pass
        return False
    return vfct

# def diffie_hellmann():
#     parameters = dh.generate_parameters(2, 512)

#     print(parameters.parameter_numbers().p, parameters.parameter_numbers().g)

# def ed25519_shared_secret(private_key, public_key):
#     # Convert the private and public keys to integers
#     private_key_int = pure25519.bytes_to_clamped_scalar(private_key)
#     public_point = pure25519.basic.decodepoint(public_key)

#     x, _ = pure25519.basic.xform_extended_to_affine(pure25519.basic.scalarmult_element_safe_slow(pure25519.basic.xform_affine_to_extended(public_point), private_key_int))

#     return pure25519.scalar_to_bytes(x)

#     #public_key_int = int.from_bytes(public_key, byteorder='little')

#     # Perform scalar multiplication using the private and public keys
#     #shared_secret_int = private_key_int * public_key_int

#     # Convert the shared secret back to bytes
#     #shared_secret = shared_secret_int.to_bytes(32, byteorder='little')
#     #return shared_secret

# def test():
#     tmp1, _ = pure25519.create_keypair()
#     tmp2, _ = pure25519.create_keypair()
#     priv1, pub1 = tmp1.sk_s[:32], tmp1.vk_s
#     priv2, pub2 = tmp2.sk_s[:32], tmp2.vk_s


#     private1 = X25519PrivateKey.from_private_bytes(Ed25519PrivateKey.from_private_bytes(priv1).private_bytes_raw())
#     public1 = X25519PublicKey.from_public_bytes(Ed25519PublicKey.from_public_bytes(pub1).public_bytes_raw())
#     private2 = X25519PrivateKey.from_private_bytes(Ed25519PrivateKey.from_private_bytes(priv2).private_bytes_raw())
#     public2 = X25519PublicKey.from_public_bytes(Ed25519PublicKey.from_public_bytes(pub2).public_bytes_raw())

#     share1 = private1.exchange(public2)
#     share2 = private2.exchange(public1)

#     print(share1 == share2)
# # eof
