# tinyISP: A Tunneling Negotiation and Feed Bundling Protocol Based on Secure Scuttlebutt

## Usage
Both, ISP and Client, needs to be connected to the same network, because data is replicated via UDP-Multicast.

### Python

python3 isp.py

Available commands:
- /me: displays the SSB-ID of the ISP.
- /follow @SSBID.ed25519: Adds the given ID to the ISPs repo and starts replicating this feed.
- /whitelist @SSBID.ed25519: Adds the given ID to the whitelist. The whitelist is disabled by default, until the first ID is added.
- /farewell @SSBID.ed25519: Terminates the contract with the given client and initates the farewell-phase.

### Android
Compile the APK file and use the GUI to interact with the ISP.
