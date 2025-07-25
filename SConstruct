import os
import subprocess
import sys
import sysconfig
import platform
import numpy as np

import SCons.Errors

SCons.Warnings.warningAsException(True)

# pending upstream fix - https://github.com/SCons/scons/issues/4461
#SetOption('warn', 'all')

TICI = os.path.isfile('/TICI')
AGNOS = TICI

Decider('MD5-timestamp')

SetOption('num_jobs', int(os.cpu_count()/2))

AddOption('--kaitai',
          action='store_true',
          help='Regenerate kaitai struct parsers')

AddOption('--asan',
          action='store_true',
          help='turn on ASAN')

AddOption('--ubsan',
          action='store_true',
          help='turn on UBSan')

AddOption('--coverage',
          action='store_true',
          help='build with test coverage options')

AddOption('--clazy',
          action='store_true',
          help='build with clazy')

AddOption('--compile_db',
          action='store_true',
          help='build clang compilation database')

AddOption('--ccflags',
          action='store',
          type='string',
          default='',
          help='pass arbitrary flags over the command line')

AddOption('--external-sconscript',
          action='store',
          metavar='FILE',
          dest='external_sconscript',
          help='add an external SConscript to the build')

AddOption('--mutation',
          action='store_true',
          help='generate mutation-ready code')

AddOption('--minimal',
          action='store_false',
          dest='extras',
          default=os.path.exists(File('#.lfsconfig').abspath), # minimal by default on release branch (where there's no LFS)
          help='the minimum build to run openpilot. no tests, tools, etc.')

## Architecture name breakdown (arch)
## - larch64: linux tici aarch64
## - aarch64: linux pc aarch64
## - x86_64:  linux pc x64
## - Darwin:  mac x64 or arm64
real_arch = arch = subprocess.check_output(["uname", "-m"], encoding='utf8').rstrip()
if platform.system() == "Darwin":
  arch = "Darwin"
  brew_prefix = subprocess.check_output(['brew', '--prefix'], encoding='utf8').strip()
elif arch == "aarch64" and AGNOS:
  arch = "larch64"
assert arch in ["larch64", "aarch64", "x86_64", "Darwin"]

lenv = {
  "PATH": os.environ['PATH'],
  "LD_LIBRARY_PATH": [Dir(f"#third_party/acados/{arch}/lib").abspath],
  "PYTHONPATH": Dir("#").abspath + ':' + Dir(f"#third_party/acados").abspath,

  "ACADOS_SOURCE_DIR": Dir("#third_party/acados").abspath,
  "ACADOS_PYTHON_INTERFACE_PATH": Dir("#third_party/acados/acados_template").abspath,
  "TERA_PATH": Dir("#").abspath + f"/third_party/acados/{arch}/t_renderer"
}

rpath = lenv["LD_LIBRARY_PATH"].copy()

if arch == "larch64":
  cpppath = [
    "#third_party/opencl/include",
  ]

  libpath = [
    "/usr/local/lib",
    "/system/vendor/lib64",
    f"#third_party/acados/{arch}/lib",
  ]

  libpath += [
    "#third_party/libyuv/larch64/lib",
    "/usr/lib/aarch64-linux-gnu"
  ]
  cflags = ["-DQCOM2", "-mcpu=cortex-a57"]
  cxxflags = ["-DQCOM2", "-mcpu=cortex-a57"]
  rpath += ["/usr/local/lib"]
else:
  cflags = []
  cxxflags = []
  cpppath = []
  rpath += []

  # MacOS
  if arch == "Darwin":
    libpath = [
      f"#third_party/libyuv/{arch}/lib",
      f"#third_party/acados/{arch}/lib",
      f"{brew_prefix}/lib",
      f"{brew_prefix}/opt/openssl@3.0/lib",
      "/System/Library/Frameworks/OpenGL.framework/Libraries",
    ]

    cflags += ["-DGL_SILENCE_DEPRECATION"]
    cxxflags += ["-DGL_SILENCE_DEPRECATION"]
    cpppath += [
      f"{brew_prefix}/include",
      f"{brew_prefix}/opt/openssl@3.0/include",
    ]
    lenv["DYLD_LIBRARY_PATH"] = lenv["LD_LIBRARY_PATH"]
  # Linux
  else:
    libpath = [
      f"#third_party/acados/{arch}/lib",
      f"#third_party/libyuv/{arch}/lib",
      "/usr/lib",
      "/usr/local/lib",
    ]

if GetOption('asan'):
  ccflags = ["-fsanitize=address", "-fno-omit-frame-pointer"]
  ldflags = ["-fsanitize=address"]
elif GetOption('ubsan'):
  ccflags = ["-fsanitize=undefined"]
  ldflags = ["-fsanitize=undefined"]
else:
  ccflags = []
  ldflags = []

# no --as-needed on mac linker
if arch != "Darwin":
  ldflags += ["-Wl,--as-needed", "-Wl,--no-undefined"]

ccflags_option = GetOption('ccflags')
if ccflags_option:
  ccflags += ccflags_option.split(' ')

env = Environment(
  ENV=lenv,
  CCFLAGS=[
    "-g",
    "-fPIC",
    "-O2",
    "-Wunused",
    "-Werror",
    "-Wshadow",
    "-Wno-unknown-warning-option",
    "-Wno-inconsistent-missing-override",
    "-Wno-c99-designator",
    "-Wno-reorder-init-list",
    "-Wno-vla-cxx-extension",
  ] + cflags + ccflags,

  CPPPATH=cpppath + [
    "#",
    "#third_party/acados/include",
    "#third_party/acados/include/blasfeo/include",
    "#third_party/acados/include/hpipm/include",
    "#third_party/catch2/include",
    "#third_party/libyuv/include",
    "#third_party/json11",
    "#third_party/linux/include",
    "#third_party",
    "#msgq",
  ],

  CC='clang',
  CXX='clang++',
  LINKFLAGS=ldflags,

  RPATH=rpath,

  CFLAGS=["-std=gnu11"] + cflags,
  CXXFLAGS=["-std=c++1z"] + cxxflags,
  LIBPATH=libpath + [
    "#msgq_repo",
    "#third_party",
    "#selfdrive/pandad",
    "#common",
    "#rednose/helpers",
  ],
  CYTHONCFILESUFFIX=".cpp",
  COMPILATIONDB_USE_ABSPATH=True,
  REDNOSE_ROOT="#",
  tools=["default", "cython", "compilation_db", "rednose_filter"],
  toolpath=["#site_scons/site_tools", "#rednose_repo/site_scons/site_tools"],
)

if arch == "Darwin":
  # RPATH is not supported on macOS, instead use the linker flags
  darwin_rpath_link_flags = [f"-Wl,-rpath,{path}" for path in env["RPATH"]]
  env["LINKFLAGS"] += darwin_rpath_link_flags

if GetOption('compile_db'):
  env.CompilationDatabase('compile_commands.json')

# Setup cache dir
cache_dir = '/data/scons_cache' if AGNOS else '/tmp/scons_cache'
CacheDir(cache_dir)
Clean(["."], cache_dir)

node_interval = 5
node_count = 0
def progress_function(node):
  global node_count
  node_count += node_interval
  sys.stderr.write("progress: %d\n" % node_count)

if os.environ.get('SCONS_PROGRESS'):
  Progress(progress_function, interval=node_interval)

# Cython build environment
py_include = sysconfig.get_paths()['include']
envCython = env.Clone()
envCython["CPPPATH"] += [py_include, np.get_include()]
envCython["CCFLAGS"] += ["-Wno-#warnings", "-Wno-shadow", "-Wno-deprecated-declarations"]
envCython["CCFLAGS"].remove("-Werror")

envCython["LIBS"] = []
if arch == "Darwin":
  envCython["LINKFLAGS"] = ["-bundle", "-undefined", "dynamic_lookup"] + darwin_rpath_link_flags
else:
  envCython["LINKFLAGS"] = ["-pthread", "-shared"]

np_version = SCons.Script.Value(np.__version__)
Export('envCython', 'np_version')

Export('env', 'arch', 'real_arch')

# Build common module
SConscript(['common/SConscript'])
Import('_common', '_gpucommon')

common = [_common, 'json11', 'zmq']
gpucommon = [_gpucommon]

Export('common', 'gpucommon')

# Build messaging (cereal + msgq + socketmaster + their dependencies)
# Enable swaglog include in submodules
env_swaglog = env.Clone()
env_swaglog['CXXFLAGS'].append('-DSWAGLOG="\\"common/swaglog.h\\""')
SConscript(['opendbc_repo/SConscript'], exports={'env': env_swaglog})

SConscript(['msgq_repo/SConscript'], exports={'env': env_swaglog})
messaging = ['capnp', 'kj',]
Export('messaging')


# Build other submodules
SConscript(['panda/SConscript'])

# Build rednose library
SConscript(['rednose/SConscript'])

# Build system services
SConscript([
  'system/ubloxd/SConscript',
  'system/loggerd/SConscript',
])
if arch != "Darwin":
  SConscript([
    'system/logcatd/SConscript',
    'system/proclogd/SConscript',
  ])

if arch == "larch64":
  SConscript(['system/camerad/SConscript'])

# Build openpilot
SConscript(['third_party/SConscript'])

SConscript(['cereal/SConscript'])
SConscript(['selfdrive/SConscript'])

if Dir('#tools/cabana/').exists() and GetOption('extras'):
  SConscript(['tools/replay/SConscript'])
  if arch != "larch64":
    SConscript(['tools/cabana/SConscript'])

external_sconscript = GetOption('external_sconscript')
if external_sconscript:
  SConscript([external_sconscript])
