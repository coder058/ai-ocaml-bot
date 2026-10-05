"""Linux-only failure injection into real OCaml fsync; never deploy this helper.

SOURCE: a six-second synthetic stall exceeds the existing five-second quote
guard. This fixture is an engineering failure case, not measured latency.
"""
import subprocess
from pathlib import Path

CODE = r'''
#define _GNU_SOURCE
#include <dlfcn.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int fsync(int fd) {
    char link[PATH_MAX], path[PATH_MAX];
    snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
    ssize_t length=readlink(link, path, sizeof(path)-1);
    const char *target=getenv("SYNTHETIC_FSYNC_TARGET");
    if (length>=0) {
        path[length]='\0';
        // SOURCE: synthetic six-second stall, longer than the five-second guard.
        if (target && strstr(path,target)) usleep(6000000);
    }
    int (*actual)(int)=dlsym(RTLD_NEXT,"fsync");
    return actual(fd);
}
'''


def environment(root: Path, target: str) -> dict[str, str]:
    source=root/'synthetic_fsync_delay.c'; library=root/'synthetic_fsync_delay.so'
    source.write_text(CODE)
    subprocess.run(['gcc','-shared','-fPIC','-o',str(library),str(source),'-ldl'],check=True,
                   capture_output=True,text=True)
    return {'LD_PRELOAD':str(library),'SYNTHETIC_FSYNC_TARGET':target}
