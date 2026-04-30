import { generateConfig } from '../configGen';

describe('generateConfig', () => {
  const cfg = {
    baseNetwork: '192.168.44',
    subnet: '24',
    gateway: '192.168.44.1',
    mgmtVlan: '10',
    cxVlan: '20',
    secVlan: '30',
    ntpServer: 'time.google.com',
  };

  it('appends interface rename commands when port labels provided', () => {
    const device = {
      hostname: 'sw1',
      ip: '192.168.44.10',
      mac: '00:11:22:33:44:55',
      model: 'CRS326-24G-2S+RM',
      portLabels: { ether2: 'Unit202' },
    };
    const out = generateConfig(device, cfg);
    expect(out).toMatch(/set \[ find name=ether2 \] name=Unit202/);
  });
});

