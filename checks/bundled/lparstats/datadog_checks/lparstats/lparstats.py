# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2018 Datadog, Inc.

from utils.process import get_subprocess_output
from utils.platform import running_root
from checks import AgentCheck


class LPARStats(AgentCheck):
    MEMORY_METRICS_START_IDX = 1
    HYPERVISOR_METRICS_START_IDX = 4
    HYPERVISOR_IDX_METRIC_MAP = {
        0: 'system.lpar.hypervisor.n_calls',
        1: 'system.lpar.hypervisor.time.spent.total',
        2: 'system.lpar.hypervisor.time.spent.hyp',
        3: 'system.lpar.hypervisor.time.call.avg',
        4: 'system.lpar.hypervisor.time.call.max',
    }
    MEMORY_ENTITLEMENTS_START_IDX = 4
    SPURR_PROCESSOR_UTILIZATION_START_IDX = 3
    DEFAULT_TIMEOUT = 5

    def check(self, instance):
        sudo = instance.get('sudo', False)
        root = running_root()
        if not root and not sudo:
            self.log.info('Not running as root or sudo - entitlement and hypervisor metrics might be unavailable')

        timeout = None
        if sudo:
            timeout = self.DEFAULT_TIMEOUT  # protect against bad sudo settings

        if instance.get('memory_stats', True):
            self.collect_memory(instance.get('page_stats', True), sudo, timeout)
        if instance.get('memory_entitlements', True) and root:
            self.collect_memory_entitlements(sudo, timeout)
        if instance.get('hypervisor', True) and root:
            self.collect_hypervisor(sudo, timeout)
        if instance.get('spurr_utilization', True):
            self.collect_spurr(sudo, timeout)

    def collect_memory(self, page_stats=True, sudo=False, timeout=None):
        cmd = ['lparstat', '-m']
        if page_stats:
            cmd.append('-pw')
        cmd.extend(['1', '1'])

        output, _, _ = get_subprocess_output(cmd, self.log, sudo=sudo, timeout=timeout)
        '''

        System configuration: lcpu=4 mem=7936MB mpsz=0.00GB iome=7936.00MB iomp=16 ent=0.20

        physb   hpi  hpit  pmem  iomin   iomu   iomf  iohwm iomaf  pgcol mpgcol ccol %entc  vcsw
        ----- ----- ----- ----- ------ ------ ------ ------ ----- ------ ------ ---- ----- -----
        0.63     0     0  7.75   46.8   23.8   -     23.9     0    0.0   0.0   0.0   4.1 1249055296

        or

        System configuration: lcpu=4 mem=7936MB mpsz=0.00GB iome=7936.00MB iomp=16 ent=0.20

        physb   hpi  hpit  pmem  iomin   iomu   iomf  iohwm iomaf %entc  vcsw
        ----- ----- ----- ----- ------ ------ ------ ------ ----- ----- -----
         0.63     0     0  7.75   46.8   -     -     -       0   4.1 1249045057
        '''
        stats = [_f for _f in output.splitlines() if _f][self.MEMORY_METRICS_START_IDX:]
        fields = [_f for _f in stats[0].split(' ') if _f]
        values = [_f for _f in stats[2].split(' ') if _f]
        for idx, field in enumerate(fields):
            try:
                m = float(values[idx])
                if '%' in field:
                    field = field.replace('%', '')
                self.gauge('system.lpar.memory.{}'.format(field), m)
            except ValueError:
                self.log.info("unable to convert %s to float - skipping", field)
                continue

    def collect_hypervisor(self, sudo=False, timeout=None):
        cmd = ['lparstat', '-H', '1', '1']
        output, _, _ = get_subprocess_output(cmd, self.log, sudo=sudo, timeout=timeout)
        '''

        System configuration: type=Shared mode=Uncapped smt=On lcpu=4 mem=7936MB psize=16 ent=0.20

                   Detailed information on Hypervisor Calls

        Hypervisor                  Number of    %Total Time   %Hypervisor   Avg Call    Max Call
          Call                        Calls         Spent      Time Spent    Time(ns)    Time(ns)

        remove                          15            0.0           0.4       1218        1781
        read                             0            0.0           0.0          0           0
        nclear_mod                       0            0.0           0.0          0           0
        page_init                      316            0.0           9.7       1452        6843
        clear_ref                        0            0.0           0.0          0           0
        protect                          0            0.0           0.0          0           0
                                                ...
                                                ...
        --------------------------------------------------------------------------------
        '''
        stats = [_f for _f in output.splitlines() if _f][self.HYPERVISOR_METRICS_START_IDX:]
        for stat in stats:
            values = [_f for _f in stat.split(' ') if _f]
            call_tag = "call:{}".format(values[0])
            for idx, entry in enumerate(values[1:]):
                try:
                    m = self.HYPERVISOR_IDX_METRIC_MAP[idx]
                    v = float(entry)
                    self.gauge(m, v, tags=[call_tag])
                except ValueError:
                    self.log.info("unable to convert %s to float for %s - skipping", m, call_tag)
                    continue

    def collect_memory_entitlements(self, sudo=False, timeout=None):
        cmd = ['lparstat', '-m', '-eR', '1', '1']
        output, _, _ = get_subprocess_output(cmd, self.log, sudo=sudo, timeout=timeout)
        '''

        System configuration: lcpu=4 mem=7936MB mpsz=0.00GB iome=7936.00MB iomp=16 ent=0.20

        physb   hpi  hpit  pmem  iomin   iomu   iomf  iohwm iomaf %entc  vcsw
        ----- ----- ----- ----- ------ ------ ------ ------ ----- ----- -----
        0.64     0     0  7.75   46.8   -     -     -       0   4.1 1250974887

                    iompn: iomin  iodes   iomu  iores  iohwm  iomaf
               ent1.txpool  2.12  16.00   2.00   2.12   2.00      0
            ent1.rxpool__4  4.00  16.00   3.50   4.00   3.50      0
            ent1.rxpool__3  4.00  16.00   2.00  16.00   2.00      0
            ent1.rxpool__2  2.50   5.00   2.00   2.50   2.00      0
            ent1.rxpool__1  0.84   2.25   0.75   0.84   0.75      0
            ent1.rxpool__0  1.59   4.25   1.50   1.59   1.50      0
              ent1.phypmem  0.10   0.10   0.09   0.10   0.09      0
               ent0.txpool  2.12  16.00   2.00   2.12   2.00      0
            ent0.rxpool__4  4.00  16.00   3.50   4.00   3.50      0
            ent0.rxpool__3  4.00  16.00   2.00  16.00   2.00      0
            ent0.rxpool__2  2.50   5.00   2.00   2.50   2.00      0
            ent0.rxpool__1  0.84   2.25   0.75   0.84   0.75      0
            ent0.rxpool__0  1.59   4.25   1.50   1.59   1.50      0
              ent0.phypmem  0.10   0.10   0.09   0.10   0.09      0
                    vscsi0 16.50  16.50   0.13  16.50   0.18      0
                      sys0  0.00   0.00   0.00   0.00   0.00      0
                    '''
        stats = [_f for _f in output.splitlines() if _f][self.MEMORY_ENTITLEMENTS_START_IDX:]
        fields = [_f for _f in stats[0].split(' ') if _f][1:]
        for stat in stats[1:]:
            values = [_f for _f in stat.split(' ') if _f]
            tag = "iompn:{}".format(values[0])
            for idx, field in enumerate(fields):
                try:
                    m = "system.lpar.memory.entitlement.{}".format(field)
                    v = float(values[idx+1])
                    self.gauge(m, v, tags=[tag])
                except ValueError:
                    self.log.info("unable to convert %s to float for %s - skipping", m, tag)
                    continue

    def collect_spurr(self, sudo=False, timeout=None):
        cmd = ['lparstat', '-E', '1', '1']
        output, _, _ = get_subprocess_output(cmd, self.log, sudo=sudo, timeout=timeout)
        '''

        System configuration: type=Shared mode=Uncapped smt=On lcpu=4 mem=7936MB ent=0.20 Power=Disabled

        Physical Processor Utilisation:

         --------Actual--------              ------Normalised------
         user   sys  wait  idle      freq    user   sys  wait  idle
         ----  ----  ----  ----   ---------  ----  ----  ----  ----
        0.008 0.012 0.000 0.180 3.6GHz[100%] 0.008 0.012 0.000 0.180
        '''
        table = [_f for _f in output.splitlines() if _f][self.SPURR_PROCESSOR_UTILIZATION_START_IDX:]
        fields = [_f for _f in table[0].split(' ') if _f]
        stats = [_f for _f in table[2].split(' ') if _f]
        metrics = {}
        total = 0
        total_norm = 0
        metric_tpl = "system.lpar.spurr.{}"
        for idx, field in enumerate(fields):
            metric = metric_tpl.format(field)
            if idx > len(fields) / 2:
                metric = "{}.norm".format(metric)

            try:
                metrics[metric] = float(stats[idx])
            except ValueError:
                self.log.info("unable to convert %s to float - skipping", metric)
                continue
            if 'norm' in metric:
                total_norm += metrics[metric]
            else:
                total += metrics[metric]

        for metric, val in metrics.items():
            if 'norm' in metric:
                val_pct = val / total_norm
            else:
                val_pct = val / total

            self.gauge(metric, val)
            self.gauge("{}.pct".format(metric), val_pct)
