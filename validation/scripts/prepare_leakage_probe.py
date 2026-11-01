"""Build-only instrumentation of the pinned secret/ciphertext basemul call.

Original sources/measurements stay untouched. Default hooks are RAM markers,
NOT GPIO triggers. No board access, flashing, or hardware leakage measurement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from run_host import ROOT, VAL, UP, PIN
from build_board import validate_elf


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--headers',type=Path,required=True,help='Existing verified test_coins.h/expected_secrets.h directory')
    p.add_argument('--arm',type=Path,help='Optional ARM compiler for offline ELF build')
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    headers=args.headers.resolve()
    logs=[]
    def run(cmd,name,cwd=ROOT):
        try:
            result=subprocess.run(list(map(str,cmd)),cwd=cwd,capture_output=True)
        except OSError as error:
            (out/(name+'.txt')).write_text(type(error).__name__+': '+str(error))
            raise
        (out/(name+'.txt')).write_bytes(result.stdout+result.stderr)
        logs.append({'name':name,'returncode':result.returncode})
        if result.returncode:raise RuntimeError(f'{name} failed; inspect {out/name}')
        return result.stdout
    pin=run(['git','-C',UP,'rev-parse','HEAD'],'pin').decode().strip()
    dirty=run(['git','-C',UP,'status','--porcelain','--untracked-files=no'],'upstream-status').strip()
    if pin!=PIN or dirty:raise RuntimeError('Upstream identity mismatch')
    source=UP/'mlkem/src/indcpa.c';text=source.read_text()
    call='  mlk_polyvec_basemul_acc_montgomery_cached(sb, skpv, b, b_cache);'
    if text.count(call)!=1:raise RuntimeError('Expected exactly one decapsulation basemul call')
    prelude='''/* LAB INSTRUMENTATION: RAM markers only, no GPIO/analog capture. */
volatile unsigned lab_probe_high, lab_probe_rises, lab_probe_falls;
static void lab_trigger_high(void) { lab_probe_high=1; ++lab_probe_rises; }
static void lab_trigger_low(void) { lab_probe_high=0; ++lab_probe_falls; }
'''
    modified=prelude+text.replace(call,'  lab_trigger_high();\n'+call+'\n  lab_trigger_low();')
    derived=out/'indcpa-probe.c';derived.write_text(modified)
    scu=UP/'mlkem/mlkem_native.c';unit=out/'mlkem-probe.c'
    unit.write_text(scu.read_text().replace('#include "src/indcpa.c"','#include "indcpa-probe.c"'))
    common=['-O2','-std=c99','-Wall','-Wextra','-Werror','-DMLK_CONFIG_NAMESPACE_PREFIX=mlkem',
            '-I'+str(UP/'mlkem'),'-I'+str(UP/'mlkem/src'),'-I'+str(headers)]
    wrapper=out/'host-probe.c'
    wrapper.write_text('#define main validation_main\n#include "'+(VAL/'src/validation.c').as_posix()+'"\n#undef main\n'
        'extern volatile unsigned lab_probe_high,lab_probe_rises,lab_probe_falls;\n'
        'int main(void) { int rc=validation_main(); if(rc) return rc;\n'
        'return (lab_probe_high || lab_probe_rises!=300 || lab_probe_falls!=300) ? 99 : 0; }\n')
    run(['gcc',*common,'-DMLK_CONFIG_PARAMETER_SET=768','-DMLK_CONFIG_NO_RANDOMIZED_API','-DHOST_VERIFY',unit,wrapper,'-o',out/'host-probe.exe'],'host-build')
    corpus=run([out/'host-probe.exe'],'host-corpus')
    archived=(VAL/'evidence/host-corpus.jsonl').read_bytes()
    if [json.loads(x) for x in corpus.splitlines()]!=[json.loads(x) for x in archived.splitlines()]:
        raise RuntimeError('Instrumented corpus differs from archived host results')
    lock=json.loads((VAL/'provenance.json').read_text())['acvp']
    vectors=VAL/'upstream/acvp'
    for name,expected in lock['sha256'].items():
        if sha(vectors/name)!=expected:raise RuntimeError('ACVP hash mismatch '+name)
    for level in (512,768,1024):
        binary=out/f'test/build/mlkem{level}/bin/acvp_mlkem{level}.exe';binary.parent.mkdir(parents=True)
        run(['gcc',*common,f'-DMLK_CONFIG_PARAMETER_SET={level}',unit,UP/'test/notrandombytes/notrandombytes.c',UP/'test/acvp/acvp_mlkem.c','-o',binary],f'acvp-build-{level}')
    cases=0
    for group in ('ML-KEM-keyGen-FIPS203','ML-KEM-encapDecap-FIPS203','ML-KEM-encapDecap-FIPS203-tr1'):
        run([sys.executable,UP/'test/acvp/acvp_client.py','--prompt',vectors/group/'prompt.json','--expected',vectors/group/'expectedResults.json','--jobs','4'],group,cwd=out)
        if 'ALL GOOD!' not in (out/(group+'.txt')).read_text():raise RuntimeError('Missing ACVP success marker')
        cases+=sum(len(g['tests']) for g in json.loads((vectors/group/'prompt.json').read_text())['testGroups'])
    result={'status':'VERIFIED HOST; PREPARED FIRMWARE; NO DEVICE RUN','upstream':PIN,
            'instrumentation':'RAM marker hooks around secret/ciphertext basemul in mlk_indcpa_dec; no GPIO adapter',
            'host_cases':100,'marker_pairs_checked':300,'acvp_cases':cases,
            'original_indcpa_sha256':sha(source),'derived_indcpa_sha256':sha(derived),
            'crypto_scope':'full ML-KEM with instrumented operation boundaries; no scalar surrogate substituted'}
    (out/'host-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    if args.arm:
        arm=args.arm.resolve();objects=[]
        flags=['-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft','-ffunction-sections','-fdata-sections','-fstack-usage']
        for src in (unit,VAL/'src/validation.c',VAL/'src/startup.S'):
            obj=out/(src.stem+'.o')
            run([arm,*common,*flags,'-DMLK_CONFIG_PARAMETER_SET=768','-DMLK_CONFIG_NO_RANDOMIZED_API','-c',src,'-o',obj],'arm-'+src.stem);objects.append(obj)
        elf=out/'mlkem768-probe.elf'
        run([arm,*flags,'-nostartfiles','-T',VAL/'src/stm32f407vg.ld','-Wl,--gc-sections','-Wl,-Map='+str(out/'probe.map'),*objects,'-lc','-lgcc','-o',elf],'arm-link')
        result['elf']=validate_elf(elf,512) # stricter bound; still does not resolve actual chip marking
        run([arm.with_name('arm-none-eabi-size.exe'),'-A',elf],'arm-size')
        run([arm.with_name('arm-none-eabi-objdump.exe'),'-d',elf],'arm-disassembly')
        run([arm.with_name('arm-none-eabi-objcopy.exe'),'-O','binary',elf,out/'probe.bin'],'arm-objcopy')
        result['firmware_bytes']=(out/'probe.bin').stat().st_size
        result['firmware_sha256']=sha(out/'probe.bin')
    result['commands']=logs
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
