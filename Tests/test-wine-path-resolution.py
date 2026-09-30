#!/usr/bin/env python3
"""Compare Wine's real pathname resolver with an independent prior implementation.

Extracts lookup_unix_name, find_file_in_dir and DOS-name helpers from the patched
Wine source. The reference resolver and search helper are pinned below, rather
than derived from the new implementation. Host shims provide UTF-16 conversion,
case-sensitive final-component probes and record reparse dispatch;
they do not emulate the contents of Windows reparse-point records. No device or
game save is touched. Generated sources, binaries, and fixtures stay in cache.
"""
import argparse
import ctypes
import datetime
import os
from pathlib import Path
import re
import subprocess


def function(source, name):
    # Match the definition, avoiding any earlier declaration or call.
    match = re.search(r"static [^{;]+\b" + name + r"\s*\([^;]+?\)\s*\{", source)
    assert match, name
    start, opening = match.start(), match.end() - 1
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


# Independent reference from Wine f91a02a18d215e359a3ddaa5806f55bfe7a5ee86,
# including the previously verified existing-parent shortcut. Do not regenerate
# this reference from working source when changing resolver/search behavior.
# Wine's file.c: Copyright 1993 Erik Bos; 2003 Eric Pouech;
# 1996, 2004 Alexandre Julliard. The copied functions are licensed under
# LGPL-2.1-or-later, without warranty; see LICENSES/Wine-LGPL-2.1.txt.
BASELINE_SOURCE = r'''
static NTSTATUS find_file_in_dir( int root_fd, char *unix_name, int pos, const WCHAR *name, int length,
                                  BOOLEAN check_case )
{
    WCHAR buffer[MAX_DIR_ENTRY_LEN];
    BOOLEAN is_name_8_dot_3;
    DIR *dir;
    struct dirent *de;
    struct stat st;
    int fd, ret;

    /* try a shortcut for this directory */

    unix_name[pos++] = '/';
    ret = ntdll_wcstoumbs( name, length, unix_name + pos, MAX_DIR_ENTRY_LEN + 1, TRUE );
    if (ret >= 0 && ret <= MAX_DIR_ENTRY_LEN)
    {
        unix_name[pos + ret] = 0;
        if (!fstatat( root_fd, unix_name, &st, 0 )) return STATUS_SUCCESS;
    }
    if (check_case) goto not_found;  /* we want an exact match */

    if (pos > 1) unix_name[pos - 1] = 0;
    else unix_name[1] = 0;  /* keep the initial slash */

    /* check if it fits in 8.3 so that we don't look for short names if we won't need them */

    is_name_8_dot_3 = is_legal_8dot3_name( name, length );
#ifndef VFAT_IOCTL_READDIR_BOTH
    is_name_8_dot_3 = is_name_8_dot_3 && length >= 8 && name[4] == '~';
#endif

    if (!is_name_8_dot_3 && !get_dir_case_sensitivity( root_fd, unix_name )) goto not_found;

    /* now look for it through the directory */

#ifdef VFAT_IOCTL_READDIR_BOTH
    if (is_name_8_dot_3)
    {
        int fd = openat( root_fd, unix_name, O_RDONLY | O_DIRECTORY );
        if (fd != -1)
        {
            KERNEL_DIRENT kde[2];

            if (ioctl( fd, VFAT_IOCTL_READDIR_BOTH, (long)kde ) != -1)
            {
                unix_name[pos - 1] = '/';
                while (kde[0].d_reclen)
                {
                    if (kde[1].d_name[0])
                    {
                        ret = ntdll_umbstowcs( kde[1].d_name, strlen(kde[1].d_name),
                                               buffer, MAX_DIR_ENTRY_LEN );
                        if (ret == length && !wcsnicmp( buffer, name, ret ))
                        {
                            strcpy( unix_name + pos, kde[1].d_name );
                            close( fd );
                            return STATUS_SUCCESS;
                        }
                    }
                    ret = ntdll_umbstowcs( kde[0].d_name, strlen(kde[0].d_name),
                                           buffer, MAX_DIR_ENTRY_LEN );
                    if (ret == length && !wcsnicmp( buffer, name, ret ))
                    {
                        strcpy( unix_name + pos,
                                kde[1].d_name[0] ? kde[1].d_name : kde[0].d_name );
                        close( fd );
                        return STATUS_SUCCESS;
                    }
                    if (ioctl( fd, VFAT_IOCTL_READDIR_BOTH, (long)kde ) == -1)
                    {
                        close( fd );
                        goto not_found;
                    }
                }
                /* if that did not work, restore previous state of unix_name */
                unix_name[pos - 1] = 0;
            }
            close( fd );
        }
        /* fall through to normal handling */
    }
#endif /* VFAT_IOCTL_READDIR_BOTH */

    if ((fd = openat( root_fd, unix_name, O_RDONLY )) == -1) return errno_to_status( errno );
    if (!(dir = fdopendir( fd )))
    {
        close( fd );
        return errno_to_status( errno );
    }

    unix_name[pos - 1] = '/';
    while ((de = readdir( dir )))
    {
        ret = ntdll_umbstowcs( de->d_name, strlen(de->d_name), buffer, MAX_DIR_ENTRY_LEN );
        if (ret == length && !wcsnicmp( buffer, name, ret ))
        {
            strcpy( unix_name + pos, de->d_name );
            closedir( dir );
            return STATUS_SUCCESS;
        }

        if (!is_name_8_dot_3) continue;

        if (!is_legal_8dot3_name( buffer, ret ))
        {
            WCHAR short_nameW[12];
            ret = hash_short_file_name( buffer, ret, short_nameW );
            if (ret == length && !wcsnicmp( short_nameW, name, length ))
            {
                strcpy( unix_name + pos, de->d_name );
                closedir( dir );
                return STATUS_SUCCESS;
            }
        }
    }
    closedir( dir );

not_found:
    unix_name[pos - 1] = 0;
    return STATUS_OBJECT_NAME_NOT_FOUND;
}

static NTSTATUS lookup_unix_name( int root_fd, OBJECT_ATTRIBUTES *attr, UNICODE_STRING *nt_name,
                                  unsigned int nt_pos, char **buffer, int unix_len, int pos,
                                  UINT disposition, BOOL open_reparse, BOOL is_unix, unsigned int reparse_count )
{
    static const WCHAR invalid_charsW[] = { INVALID_NT_CHARS, '/', 0 };
    const WCHAR *name = attr->ObjectName->Buffer + nt_pos;
    unsigned int name_len = (attr->ObjectName->Length / sizeof(WCHAR)) - nt_pos;
    NTSTATUS status;
    int ret;
    struct stat st;
    char *unix_name = *buffer;
    const WCHAR *ptr, *end;

    /* check syntax of individual components */

    for (ptr = name, end = name + name_len; ptr < end; ptr++)
    {
        if (*ptr == '\\') return STATUS_OBJECT_NAME_INVALID;  /* duplicate backslash */
        if (*ptr == '.')
        {
            if (ptr + 1 == end) return STATUS_OBJECT_NAME_INVALID;  /* "." element */
            if (ptr[1] == '\\') return STATUS_OBJECT_NAME_INVALID;  /* "." element */
            if (ptr[1] == '.')
            {
                if (ptr + 2 == end) return STATUS_OBJECT_NAME_INVALID;  /* ".." element */
                if (ptr[2] == '\\') return STATUS_OBJECT_NAME_INVALID;  /* ".." element */
            }
        }
        /* check for invalid characters (all chars except 0 are valid for unix) */
        for ( ; ptr < end && *ptr != '\\'; ptr++)
        {
            if (!*ptr) return STATUS_OBJECT_NAME_INVALID;
            if (is_unix) continue;
            if (*ptr < 32 || wcschr( invalid_charsW, *ptr )) return STATUS_OBJECT_NAME_INVALID;
        }
    }

    /* try a shortcut first */

    unix_name[pos] = '/';
    ret = ntdll_wcstoumbs( name, name_len, unix_name + pos + 1, unix_len - pos - 1, TRUE );
    if (ret >= 0 && ret < unix_len - pos - 1)
    {
        char *p;
        unix_name[pos + 1 + ret] = 0;
        for (p = unix_name + pos ; *p; p++) if (*p == '\\') *p = '/';
        if (!fstatat( root_fd, unix_name, &st, 0 ))
        {
            if (disposition == FILE_CREATE) return STATUS_OBJECT_NAME_COLLISION;
            return STATUS_SUCCESS;
        }

        /* A missing leaf need not make us resolve every existing parent again.
         * Keep the normal leaf lookup below, including case-insensitive and
         * reparse-point handling; neither names nor lookup results are cached.
         * Unix names and trailing separators retain the original path. */
        for (end = name + name_len; end > name && end[-1] != '\\'; end--) {}
        if (!is_unix && end > name && end < name + name_len)
        {
            p = strrchr( unix_name + pos, '/' );
            *p = 0;
            if (!fstatat( root_fd, unix_name, &st, 0 ) && S_ISDIR( st.st_mode ))
            {
                nt_pos += end - name;
                name_len -= end - name;
                name = end;
                pos = p - unix_name;
            }
            *p = '/';
        }
    }

    if (!name_len)  /* empty name -> drive root doesn't exist */
        return STATUS_OBJECT_PATH_NOT_FOUND;
    if (is_unix && (disposition == FILE_OPEN || disposition == FILE_OVERWRITE))
        return STATUS_OBJECT_NAME_NOT_FOUND;

    /* now do it component by component */

    while (name_len)
    {
        const WCHAR *end, *next;
        WCHAR *reparse_name;

        end = name;
        while (end < name + name_len && *end != '\\') end++;
        next = end;
        if (next < name + name_len) next++;
        name_len -= next - name;

        /* grow the buffer if needed */

        if (unix_len - pos < MAX_DIR_ENTRY_LEN + 3)
        {
            char *new_name;
            unix_len += 2 * MAX_DIR_ENTRY_LEN;
            if (!(new_name = realloc( unix_name, unix_len ))) return STATUS_NO_MEMORY;
            unix_name = *buffer = new_name;
        }

        status = find_file_in_dir( root_fd, unix_name, pos, name, end - name, is_unix );

        /* try to resolve it as a reparse point */
        if (status == STATUS_OBJECT_NAME_NOT_FOUND && (reparse_name = malloc( (end - name + 1) * sizeof(WCHAR) )))
        {
            int reparse_fd;

            memcpy( reparse_name, name, (end - name) * sizeof(WCHAR) );
            reparse_name[end - name] = '?';

            if (!name_len && open_reparse)
            {
                status = find_file_in_dir( root_fd, unix_name, pos, reparse_name, end - name + 1, is_unix );
            }
            else
            {
                if (!find_file_in_dir( root_fd, unix_name, pos, reparse_name, end - name + 1, is_unix )
                    && (reparse_fd = openat( root_fd, unix_name, O_RDONLY )) >= 0)
                {
                    status = resolve_reparse_point( reparse_fd, root_fd, attr, nt_name, nt_pos, next - name, buffer,
                                                    unix_len, pos, disposition, open_reparse, is_unix, reparse_count );
                    close( reparse_fd );
                    free( reparse_name );
                    return status;
                }
            }
            free( reparse_name );
        }

        /* if this is the last element, not finding it is not necessarily fatal */
        if (!name_len)
        {
            if (status == STATUS_OBJECT_NAME_NOT_FOUND)
            {
                if (disposition != FILE_OPEN && disposition != FILE_OVERWRITE)
                {
                    ret = ntdll_wcstoumbs( name, end - name, unix_name + pos + 1, MAX_DIR_ENTRY_LEN + 1, TRUE );
                    if (ret > 0 && ret <= MAX_DIR_ENTRY_LEN)
                    {
                        unix_name[pos] = '/';
                        pos += ret + 1;
                        if (end < next) unix_name[pos++] = '/';
                        unix_name[pos] = 0;
                        status = STATUS_NO_SUCH_FILE;
                        break;
                    }
                }
            }
            else if (status == STATUS_SUCCESS && disposition == FILE_CREATE)
            {
                status = STATUS_OBJECT_NAME_COLLISION;
            }
            if (end < next) strcat( unix_name, "/" );
        }
        else if (status == STATUS_OBJECT_NAME_NOT_FOUND) status = STATUS_OBJECT_PATH_NOT_FOUND;

        if (status != STATUS_SUCCESS) break;

        pos += strlen( unix_name + pos );
        nt_pos += next - name;
        name = next;
    }

    return status;
}
'''


PRELUDE = r'''
#include <assert.h>
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <iconv.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <wctype.h>
typedef uint16_t WCHAR;
typedef WCHAR *LPWSTR;
typedef const WCHAR *LPCWSTR;
typedef unsigned long ULONG;
typedef unsigned int UINT;
typedef int NTSTATUS, BOOL, BOOLEAN;
typedef struct { WCHAR *Buffer; unsigned short Length, MaximumLength; } UNICODE_STRING;
typedef struct { UNICODE_STRING *ObjectName; } OBJECT_ATTRIBUTES;
#define TRUE 1
#define FALSE 0
#define STATUS_SUCCESS 0
#define STATUS_OBJECT_NAME_NOT_FOUND 1
#define STATUS_OBJECT_PATH_NOT_FOUND 2
#define STATUS_OBJECT_NAME_INVALID 3
#define STATUS_OBJECT_NAME_COLLISION 4
#define STATUS_NO_MEMORY 5
#define STATUS_NO_SUCH_FILE 6
#define REPARSE_DISPATCHED 7
#define FILE_OPEN 1
#define FILE_OVERWRITE 2
#define FILE_CREATE 3
#define INVALID_NT_CHARS '*','?','<','>','|','"'
#define INVALID_DOS_CHARS INVALID_NT_CHARS,'+','=',',',';','[',']',' ','\345'
#define MAX_DIR_ENTRY_LEN 255
static int is_case_sensitive = TRUE, fault_mode;
static int stat_calls, reparse_calls, case_calls, open_calls, close_calls, rewind_calls;
static int live_fds, tracked_fds[65536];
static unsigned reparse_nt_pos, reparse_len_seen;
/* The host volume may be case-insensitive. Force only final-component exact
 * probes to miss mismatched case so the real Wine directory search is tested.
 * These host-shim reads are deliberately excluded from resolver call counts. */
static int final_component_exists_exactly(int root_fd,const char *path) {
    char copy[8192];snprintf(copy,sizeof(copy),"%s",path);
    size_t length=strlen(copy);while(length>1 && copy[length-1]=='/')copy[--length]=0;
    char *leaf=strrchr(copy,'/');if(!leaf || !leaf[1])return 1;
    *leaf++=0;int fd=openat(root_fd,copy[0]?copy:"/",O_RDONLY);
    if(fd<0)return 1;
    DIR *dir=fdopendir(fd);if(!dir){close(fd);return 1;}
    struct dirent *entry;int found=0;
    while((entry=readdir(dir)))if(!strcmp(entry->d_name,leaf)){found=1;break;}
    closedir(dir);return found;
}
static int measured_fstatat(int fd, const char *p, struct stat *s, int flags) {
    stat_calls++;int result=fstatat(fd,p,s,flags);
    if(!result && is_case_sensitive && !final_component_exists_exactly(fd,p)) {
        errno=ENOENT;return -1;
    }
    return result;
}
static int measured_openat(int root_fd,const char *p,int flags) {
    open_calls++;
    if(fault_mode==1 || (fault_mode==3 && p[0] && p[strlen(p)-1]=='?')) {
        errno=EACCES;return -1;
    }
    int fd=openat(root_fd,p,flags);
    if(fd>=0){assert(fd<65536 && !tracked_fds[fd]);tracked_fds[fd]=1;live_fds++;}
    return fd;
}
static DIR *measured_fdopendir(int fd) {
    if(fault_mode==2){errno=EMFILE;return NULL;}
    return fdopendir(fd);
}
static int measured_close(int fd) {
    if(fd>=0 && tracked_fds[fd]){tracked_fds[fd]=0;live_fds--;close_calls++;}
    return close(fd);
}
static int measured_closedir(DIR *dir) {
    int fd=dirfd(dir);assert(fd>=0 && tracked_fds[fd]);
    tracked_fds[fd]=0;live_fds--;close_calls++;
    return closedir(dir);
}
static void measured_rewinddir(DIR *dir) { rewind_calls++;rewinddir(dir); }
static void *measured_malloc(size_t size) { return fault_mode==4 ? NULL:malloc(size); }
static void *measured_realloc(void *p,size_t size) { return fault_mode==5 ? NULL:realloc(p,size); }
#define openat measured_openat
#define fdopendir measured_fdopendir
#define close measured_close
#define closedir measured_closedir
#define rewinddir measured_rewinddir
#define malloc measured_malloc
#define realloc measured_realloc
#define fstatat measured_fstatat
void configure(int sensitive,int fault) {
    assert(live_fds==0);is_case_sensitive=sensitive;fault_mode=fault;
}
static WCHAR *wide_find(const WCHAR *s,WCHAR c) {
    do { if(*s==c)return (WCHAR *)s; } while(*s++); return NULL;
}
#define wcschr wide_find
static int wcsnicmp(const WCHAR *a,const WCHAR *b,int n) {
    while(n--) { if(towlower(*a)!=towlower(*b))return 1; a++;b++; } return 0;
}
static int is_invalid_dos_char(WCHAR c) {
    static const WCHAR bad[]={INVALID_DOS_CHARS,0}; return c<32 || wide_find(bad,c)!=NULL;
}
static int convert(const char *from,const char *to,const void *src,size_t n,void *dst,size_t cap) {
    iconv_t cd=iconv_open(to,from); assert(cd!=(iconv_t)-1);
    char *in=(char *)src,*out=dst;size_t remain=cap;
    size_t result=iconv(cd,&in,&n,&out,&remain);iconv_close(cd);
    return result==(size_t)-1 ? -1 : (int)(cap-remain);
}
static int ntdll_wcstoumbs(const WCHAR *s,int n,char *d,int cap,BOOL strict) {
    (void)strict;return convert("UTF-16LE","UTF-8",s,n*2,d,cap);
}
static int ntdll_umbstowcs(const char *s,int n,WCHAR *d,int cap) {
    int r=convert("UTF-8","UTF-16LE",s,n,d,cap*2);return r<0 ? r:r/2;
}
static BOOLEAN get_dir_case_sensitivity(int fd,const char *p) {
    (void)fd;(void)p;case_calls++;return is_case_sensitive;
}
static NTSTATUS errno_to_status(int e) { return 100+e; }
static NTSTATUS resolve_reparse_point(int fd,int root_fd,OBJECT_ATTRIBUTES *attr,
    UNICODE_STRING *nt_name,unsigned nt_pos,unsigned reparse_len,char **unix_name,
    int unix_len,int pos,UINT disposition,BOOL open_reparse,BOOL is_unix,unsigned count) {
    (void)fd;(void)root_fd;(void)attr;(void)nt_name;(void)unix_name;(void)unix_len;
    (void)pos;(void)disposition;(void)open_reparse;(void)is_unix;(void)count;
    assert(live_fds==1); /* Only the reparse file, never the parent DIR. */
    reparse_calls++;reparse_nt_pos=nt_pos;reparse_len_seen=reparse_len;
    return REPARSE_DISPATCHED;
}
'''

WRAPPER = r'''
struct result { int status,stats,reparses,cases,opens,closes,rewinds,live;
                unsigned nt_pos,reparse_len;char path[4096]; };
static void run(int optimized,const char *root,const char *input,unsigned nt_pos,
                int disposition,int open_reparse,int is_unix,struct result *out) {
    WCHAR wide[2048];int len=ntdll_umbstowcs(input,strlen(input),wide,2047);assert(len>=0);
    wide[len]=0;UNICODE_STRING name={wide,len*2,(len+1)*2};OBJECT_ATTRIBUTES attr={&name};
    UNICODE_STRING nt_name={0};int size=fault_mode==5?(int)strlen(root)+2:8192;
    char *path=calloc(size,1);strcpy(path,root);
    assert(live_fds==0);
    stat_calls=reparse_calls=case_calls=open_calls=close_calls=rewind_calls=0;
    reparse_nt_pos=reparse_len_seen=0;
    out->status=(optimized?lookup_unix_name:lookup_unix_name_baseline)(AT_FDCWD,&attr,
        &nt_name,nt_pos,&path,size,strlen(path),disposition,open_reparse,is_unix,0);
    out->stats=stat_calls;out->reparses=reparse_calls;out->nt_pos=reparse_nt_pos;
    out->cases=case_calls;out->opens=open_calls;out->closes=close_calls;
    out->rewinds=rewind_calls;out->live=live_fds;
    assert(live_fds==0);
    out->reparse_len=reparse_len_seen;snprintf(out->path,sizeof(out->path),"%s",path);
    free(path);
}
void baseline(const char *r,const char *p,unsigned n,int d,int o,int u,struct result *out) {
    run(0,r,p,n,d,o,u,out);
}
void optimized(const char *r,const char *p,unsigned n,int d,int o,int u,struct result *out) {
    run(1,r,p,n,d,o,u,out);
}
void short_name(const char *input,char *out) {
    WCHAR wide[256],short_wide[12];
    int len=ntdll_umbstowcs(input,strlen(input),wide,255);
    int short_len=hash_short_file_name(wide,len,short_wide);
    int bytes=ntdll_wcstoumbs(short_wide,short_len,out,64,TRUE);assert(bytes>=0);
    out[bytes]=0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--wine", type=Path)
    args = parser.parse_args()
    wine = args.wine or args.cache / "sources/Madeira/wine"
    source = (wine / "dlls/ntdll/unix/file.c").read_text()
    resolver = function(source, "lookup_unix_name")
    baseline = BASELINE_SOURCE.replace("find_file_in_dir(", "find_file_in_dir_baseline(")
    baseline = baseline.replace("lookup_unix_name(", "lookup_unix_name_baseline(")
    context = re.search(r"struct file_lookup_dir\s*\{.*?\};", source, re.S)
    assert context, "Expected the per-component directory lookup context"
    harness = PRELUDE + "\n" + "\n".join(function(source, name) for name in
        ("hash_short_file_name", "is_legal_8dot3_name"))
    harness += "\n" + baseline + "\n" + context.group() + "\n"
    harness += function(source, "find_file_in_dir") + "\n" + resolver + "\n" + WRAPPER
    output = args.cache / "diagnostics/madeira" / ("path-resolution-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    output.mkdir(parents=True)
    (output / "resolver.c").write_text(harness)
    library = output / "resolver.dylib"
    env = dict(os.environ, TMPDIR=str(output))
    # Wine intentionally initializes its 32-byte DOS hash alphabet without a NUL.
    subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
        "-Wno-unterminated-string-initialization",
        "-fsanitize=undefined", "-fno-sanitize-recover=all", "-dynamiclib", str(output / "resolver.c"),
        "-liconv", "-o", str(library)], env=env, check=True)
    lib = ctypes.CDLL(str(library))

    class Result(ctypes.Structure):
        _fields_ = [("status", ctypes.c_int), ("stats", ctypes.c_int), ("reparses", ctypes.c_int),
                    ("cases", ctypes.c_int), ("opens", ctypes.c_int), ("closes", ctypes.c_int),
                    ("rewinds", ctypes.c_int), ("live", ctypes.c_int),
                    ("nt_pos", ctypes.c_uint), ("reparse_len", ctypes.c_uint), ("path", ctypes.c_char * 4096)]

    root = output / "fixture"
    parent = root / "users/mobile/AppData/Roaming/Glaiel Games/Mewgenics/profile/saves"
    parent.mkdir(parents=True)
    (root / "UTF8-é/猫").mkdir(parents=True)
    (root / "NotDirectory").write_text("file")
    (parent / "Existing.TXT").write_text("exists")
    (parent / "reparse?").write_text("reparse record placeholder")
    (parent / "MixedAlias?").write_text("case-insensitive reparse alias")
    (parent / "Primary.TXT").write_text("ordinary name wins")
    (parent / "primary.txt?").write_text("must not shadow ordinary name")
    (parent / "dangling").symlink_to("absent-target")
    (root / "parent-reparse?").write_text("reparse record placeholder")
    (root / "native-link").symlink_to(parent, target_is_directory=True)
    prefix = str(parent.relative_to(root)).replace("/", "\\")
    checked = 0

    def compare(path, disposition=1, open_reparse=0, is_unix=0, nt_pos=0, expected=None):
        nonlocal checked
        results = []
        for fn in (lib.baseline, lib.optimized):
            result = Result()
            fn(str(root).encode(), path.encode(), nt_pos, disposition, open_reparse, is_unix, ctypes.byref(result))
            results.append(result)
        a, b = results
        # Failure buffers are private scratch; only successful names are observable.
        visible = lambda r: (r.status, r.reparses, r.nt_pos, r.reparse_len,
                             bytes(r.path) if r.status in (0, 6, 7) else None)
        assert visible(a) == visible(b), (path, disposition, open_reparse, visible(a), visible(b))
        assert a.stats == b.stats, (path, "fresh stat count changed", a.stats, b.stats)
        assert a.live == b.live == 0, (path, "descriptor leak", a.live, b.live)
        if expected is not None:
            assert b.status == expected, (path, b.status, expected)
        checked += 1
        return a, b

    candidates = [prefix + "\\steamcampaign02.sav-journal", prefix + "\\Existing.TXT",
                  prefix + "\\existing.txt", prefix + "\\reparse", prefix + "\\mixedalias",
                  prefix + "\\primary.txt", prefix + "\\dangling", prefix + "\\missing\\leaf",
                  prefix + "\\missing\\", prefix + "\\", "MissingParent\\leaf",
                  "NotDirectory\\leaf", "UTF8-é\\猫\\missing-é🐈", "native-link\\missing",
                  "parent-reparse\\leaf", "single-missing", "", "users\\.\\leaf",
                  "users\\..\\leaf", "users\\\\leaf", "users\\invalid?leaf"]
    for sensitive in (0, 1):
        lib.configure(sensitive, 0)
        for candidate in candidates:
            for disposition in (1, 2, 3):
                for open_reparse in (0, 1):
                    compare(candidate, disposition, open_reparse)
        a, b = compare(prefix + "\\steamcampaign02.sav-journal", expected=1)
        assert (a.stats, b.stats, a.cases, b.cases) == (4, 4, 2, 1)
        if sensitive:
            assert (a.opens, b.opens, a.closes, b.closes, b.rewinds) == (2, 1, 2, 1, 1)
        else:
            assert (a.opens, b.opens, b.rewinds) == (0, 0, 0)
    lib.configure(1, 0)
    compare("ignored\\" + prefix + "\\reparse", nt_pos=8)
    compare(prefix + "\\reparse", expected=7)
    compare(prefix + "\\reparse", open_reparse=1, expected=0)
    a, b = compare(prefix + "\\mixedalias", expected=7)
    assert b.rewinds == 1, "Case-insensitive alias must rescan the retained directory"
    compare(prefix + "\\mixedalias", open_reparse=1, expected=0)
    a, b = compare(prefix + "\\primary.txt", expected=0)
    assert b.reparses == 0 and bytes(b.path).endswith(b"Primary.TXT")
    compare(prefix + "\\primary.txt", disposition=3, expected=4)
    a, b = compare(prefix + "\\Existing.TXT", expected=0)
    assert (a.stats, b.stats, a.cases, b.cases, a.opens, b.opens) == (1, 1, 0, 0, 0, 0)
    long_name = "A long filename.txt"
    (parent / long_name).write_text("DOS alias fixture")
    alias = ctypes.create_string_buffer(64)
    lib.short_name(long_name.encode(), alias)
    compare(prefix + "\\" + alias.value.decode(), expected=0)
    (parent / (alias.value.decode() + "?")).write_text("must not shadow DOS alias")
    a, b = compare(prefix + "\\" + alias.value.decode(), expected=0)
    assert b.reparses == 0 and bytes(b.path).endswith(long_name.encode())
    (parent / alias.value.decode()).write_text("literal DOS name wins exact probe")
    a, b = compare(prefix + "\\" + alias.value.decode(), expected=0)
    assert bytes(b.path).endswith(alias.value)
    for is_unix in (0, 1):
        for disposition in (1, 2, 3):
            compare(prefix + "\\missing", disposition, is_unix=is_unix)
            compare("users/mobile/missing", disposition, is_unix=is_unix)
    leaf = parent / "steamcampaign02.sav-wal"
    path = prefix + "\\" + leaf.name
    compare(path, expected=1)
    leaf.write_text("new transaction")
    compare(path, expected=0)
    leaf.unlink()
    compare(path, expected=1)
    # Allocation and filesystem errors must close any retained stream. These
    # failures target equivalent first operations rather than removed retries.
    for fault, candidate, expected in ((1, "absent", 100 + 13), (2, "absent", 100 + 24),
                                       (3, "reparse", 1), (4, "absent", 1), (5, "absent", 5)):
        lib.configure(1, fault)
        compare(prefix + "\\" + candidate, expected=expected)
    lib.configure(1, 0)
    # Repeated lookups cannot accumulate descriptors or persist misses.
    descriptors_before = len(os.listdir("/dev/fd"))
    for _ in range(200):
        compare(path, expected=1)
        compare(prefix + "\\mixedalias", expected=7)
    assert len(os.listdir("/dev/fd")) == descriptors_before
    counts = compare(prefix + "\\steamcampaign02.sav-journal", expected=1)
    parent.rename(parent.with_name("previous-saves"))
    compare(path, expected=2)
    parent.mkdir()
    leaf.write_text("new directory and transaction")
    compare(path, expected=0)
    a, b = counts
    summary = f"PASS {checked} independent resolver parity cases; missing sidecar fstatat {a.stats} -> {b.stats}, "
    summary += f"parent opens {a.opens} -> {b.opens}, sensitivity queries {a.cases} -> {b.cases}.\n"
    summary += "Exact-success path: one stat, zero directory opens/queries. No retained descriptor leaks.\n"
    summary += "Both case modes, alias/short-name precedence, allocation/I/O failures, fresh create/delete; UBSan enabled.\n"
    summary += "Actual Wine resolver/helpers; UTF-16, final-component case probes and reparse dispatch use host shims.\n"
    (output / "result.txt").write_text(summary)
    print(summary + str(output))


if __name__ == "__main__":
    main()
