#!/usr/bin/env python3

'''
This file is created by Descript to document and augment
the FFmpeg building process, for use in Descript's environment.

(1) Call build-ffmpeg with the build command
(2) Copy or generate dSYM symbol files to the workspace folder
(3) Copy executables from the workspace folder and all built dependencies to platform output folder
(4) Fix dyld ids and loader paths for all built libraries
(5) Zip up the build artifacts
'''

import glob
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import zipfile

#
#   Constants
#
cwd = os.path.dirname(os.path.realpath(__file__))
base_dir = pathlib.Path(cwd).parent.absolute()
packages_dir = os.path.join(base_dir, 'packages')
workspace_dir = os.path.join(base_dir, 'workspace')
workspace_bin_dir = os.path.join(workspace_dir, 'bin')
workspace_lib_dir = os.path.join(workspace_dir, 'lib')
os.environ["LD_LIBRARY_PATH"] = workspace_lib_dir
#
#   Keep track of which libraries are copied, skipped, or missing
#
skipped_libs = set()
copied_libs = set()
missing_libs = set()

#
#   Global Logging File
#
log_file = None

#
#
#
def log(str):
    """
    Logs to stdout and to log_file
    """
    log_file.write(str + '\n')
    print(str, flush=True)

#
#
#
def log_pipe(pipe):
    """
    logs from a pipe by calling log()
    """
    for line in iter(pipe.readline, b''): # b'\n'-separated lines
        log(line.decode('utf-8').strip())

#
#
#
def buildFFmpeg(script_dir, log_file):
    """
    builds FFmpeg and logs output to `log_file`
    """
    # set environment variables
    env = os.environ
    env['SKIPINSTALL'] = 'yes'  # append 'SKIPINSTALL=yes' to skip prompt for installing FFmpeg to /usr/local/bin/etc
    env['VERBOSE'] = 'yes'
    env['MACOSX_DEPLOYMENT_TARGET'] = deployment_target
    
    # call main build script
    build_ffmpeg_path = os.path.join(script_dir, 'build-ffmpeg')
    args = [
        build_ffmpeg_path,
        '-b',                       # build
        '--full-shared',            # custom Descript shim to build shared libraries instead of static
        '--enable-gpl-and-free']    # custom Descript shim to build GPL but not non-free (libpostproc is needed by Beamcoder and requires GPL)
    log(' '.join(args) + '\n')
    log_file.flush()
    shell_proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    with shell_proc.stdout:
        log_pipe(shell_proc.stdout)
    exitcode = shell_proc.wait() # 0 means success
    if (exitcode != 0):
        raise exitcode
#
#
#
def copyOrGenerateSymbolFile(file, dest, log_file):
    """
    Copies a single symbol file to the workspace destination
    skips symlinks to avoid duplication
    Copies entire `dSYM` packages for `dylib` files already within `.dSYM` packages
    """
    fileref = pathlib.Path(file)
    if not fileref.is_symlink():
        symbolFileName = fileref.name + '.dbg'
        destPath = os.path.join(dest, symbolFileName)
        
        # See if there's a matching pre-existing symbol file.
        # If so, copy it, replacing the destination
        # example:
        #   ./packages/libtheora-1.1.1/lib/.libs/libtheoraenc.1.dylib.dSYM/Contents/Resources/DWARF/libtheoraenc.1.dylib
        try:
            allParts = fileref.parts
            symbolDirIndex = allParts.index(symbolFileName) # throws ValueError if not in allParts
            symbolDirParts = allParts[:symbolDirIndex + 1]
            symbolDir = os.path.join(*symbolDirParts)
            if os.path.exists(destPath):
                shutil.rmtree(destPath)
            shutil.copytree(symbolDir, destPath)

        # Otherwise, generate a symbol file and place it at the destination
        # example:
        #   ./packages/libtheora-1.1.1/lib/.libs/libtheora.dylib
        except ValueError as e:
            args = ['/usr/bin/objcopy', '--only-keep-debug', str(fileref), destPath]
            log(' '.join(args) + '\n')
            process_result = subprocess.run(args, stdout=subprocess.PIPE)
            log(process_result.stdout.decode('utf-8'))

#
#
#
def copyOrGenerateSymbolFiles(source, dest, log_file):
    """
    Recursively copies symbol files to the workspace destination
    skips symlinks to avoid duplication
    Copies entire `dbg` packages for `so` files already within `.dbg` packages
    """
    for fileref in pathlib.Path(source + '/').glob('**/*.so'):
      copyOrGenerateSymbolFile(str(fileref), dest, log_file)
    for fileref in pathlib.Path(source + '/').glob('**/*.so*'):
      copyOrGenerateSymbolFile(str(fileref), dest, log_file)

#
#
#
def copyLibraryAndSymbolPackage(src_file, dest_folder, overwrite):
    """
    Copies a library and its corresponding `.dbg` bundle
    (if present)
    """
    dest_file = os.path.join(dest_folder, os.path.basename(src_file))
    
    # copy file
    if overwrite and os.path.exists(dest_file):
        os.remove(dest_file)
    shutil.copy2(src_file, dest_file, follow_symlinks=False)

    # copy symbol file
    src_symbol_package = src_file + '.dbg'
    if os.path.exists(src_symbol_package):
        dest_symbol_package = os.path.join(dest_folder, os.path.basename(src_symbol_package))
        if overwrite and os.path.exists(dest_symbol_package):
          shutil.rmtree(dest_symbol_package)
        if not os.path.exists(dest_symbol_package):
          shutil.copytree(src_symbol_package, dest_symbol_package)
        args = ['/usr/bin/strip', dest_file]
        log(' '.join(args) + '\n')
        process_result = subprocess.run(args, stdout=subprocess.PIPE)
        log(process_result.stdout.decode('utf-8'))
          
#
#
#
def getFileBaseNameWithoutVersion(file_path) -> str:
    """
    :return: `'libpostproc'` for something like `'/foo/bar/libpostproc.so.55.9.100'`
    """
    base_name = os.path.basename(file_path)
    base_name = base_name.split('.')[0] # keep everything before first '.'
    # libSDL2 weirdly has hypthen after then name (i.e., libSDL2-2.0.0.dylib)
    if base_name.startswith('libSDL2'):
        base_name = 'libSDL2'
    return base_name

#
#
#
def getVersionVariantsForFile(file_path):
    """
    Returns the following three files for any one of the file paths provided:
    `'.../ffmpeg-build-script/workspace/lib/libavcodec.so.58.134.100'`
    `'.../ffmpeg-build-script/workspace/lib/libavcodec.so.58'`
    `'.../ffmpeg-build-script/workspace/lib/libavcodec.so'`

    """
    result = set()
    result.add(file_path)
    if (pathlib.Path(file_path).is_symlink()):
        result.add(os.path.realpath(file_path))

    dependency_name_without_version = getFileBaseNameWithoutVersion(file_path)
    unversioned_dependency_base_name = os.path.join(
        os.path.dirname(file_path),
        dependency_name_without_version)

    for variant in glob.glob(unversioned_dependency_base_name + r'*.so*'):
        result.add(variant)
        
    return list(result)

#
#
#
def copyLibraryAndDependencies(src_file, dest_folder, log_file, parent_path = ''):
    """
    Recursive function to copy a library and its (non-system) dependencies
    also fixes loader paths for each library to be `@loader_path`
    :param: `parent_path` - optional argument to show which parent is linking against `src_file`
    """

    dest_file = os.path.join(dest_folder, os.path.basename(src_file))

    # copy file
    copyLibraryAndSymbolPackage(src_file, dest_folder, True)
    copied_libs.add(src_file)
    copied_libs.add(dest_file)

    # identifier for _this_ library
    this_id = ''

    # recursively copy dependencies
    args = ['/usr/bin/ldd', src_file]
    otool_proc = subprocess.Popen(args, stdout=subprocess.PIPE)
    loader_paths_to_rewrite = []
    for line in otool_proc.stdout:
        ln = line.decode('utf-8').strip()
        match = re.match('.*=> ([^\s]+) \(.*\)', ln)
        if not match:
            continue
        src_dependency_file = match.group(1)

        if src_dependency_file.startswith('/usr/local'):
            # the build grabbed libraries installed on this machine
            # which might not be available on other machines
            missing_libs.add(f'{src_dependency_file} (dependency of {os.path.basename(parent_path)})')
        elif src_dependency_file.startswith(workspace_dir):
            dependency_name = os.path.basename(src_dependency_file)
            if not len(this_id):
                # first dependency is the identifier for this library
                this_id = dependency_name
            dest_dependency_path = os.path.join(dest_folder, dependency_name)
            if not src_dependency_file in copied_libs:
                if src_dependency_file != dest_dependency_path:
                    # Copy each version variant file (often symlinks)
                    for variant_src_file in getVersionVariantsForFile(src_dependency_file):
                        copyLibraryAndSymbolPackage(variant_src_file, dest_folder, False)
                        variant_dest_file = os.path.join(dest_folder, os.path.basename(variant_src_file))
                        copied_libs.add(variant_src_file)
                        copied_libs.add(variant_dest_file)

                    # RECURSIVELY copy dependencies
                    copyLibraryAndDependencies(
                        os.path.realpath(src_dependency_file),
                        dest_folder,
                        log_file,
                        src_file)
            
            loader_paths_to_rewrite.append({'old_path': src_dependency_file, 'new_path': dest_dependency_path})
        else:
            skipped_libs.add(src_dependency_file)

#
#
#
def readVersion() -> str:
    """
    Reads the version string from ../build-ffmpeg
    :return: something like `'1.31rc1'`
    """
    result = ''
    with open(os.path.join(base_dir, 'build-ffmpeg')) as f:
        lines = f.readlines()
        for line in lines:
            if line.startswith('SCRIPT_VERSION='):
                result = line[15:].strip()
    return result

#
#
#
def getPlatformMachineVersion() -> str:
    """
    :return: a string like `'darwin-x86_64.1.31rc2'`
    """
    return sys.platform + '-' + platform.machine() + '.' + readVersion()


#
#
#
def generateChecksum(output_folder):
    """
    Calculates checksums for every file in `output_folder`
    and puts it in a `SHAMSUM256.txt` file
    """
    checksums = set()

    # calculate checksums for all files
    for (dirpath, dirnames, filenames) in os.walk(output_folder):
        for file in filenames:
            args = ['shasum', '-a', '256', os.path.join(dirpath, file)]
            output = subprocess.check_output(args)
            checksum = output.decode('utf-8').strip()

            # replace absolute path to just filename
            # From: '0a88d3f97f356c6a42449fd548f9b586f565899144849019014e36c7683b745e  /Users/cvanwink/Source/git/electron/src/out/Testing/dist.zip'
            # To:   '0a88d3f97f356c6a42449fd548f9b586f565899144849019014e36c7683b745e  *electron-v13.1.6-darwin-x64.zip'
            checksum = checksum.replace(os.path.join(dirpath, ''), '*')
            checksums.add(checksum)
        break
    
    # Write Checksums to file
    checksum_file_path = os.path.join(output_folder, 'SHAMSUM256.txt')
    checksum_file = open(checksum_file_path, 'w')
    for checksum in checksums:
        checksum_file.write(f'{checksum}\n')
    checksum_file.close()

#
#
#
def main():
    output_dir = os.path.join(cwd, sys.platform)
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    temp_dir = os.path.join(output_dir, platform.machine())
    os.makedirs(temp_dir)
    symbol_temp_dir = os.path.join(output_dir, platform.machine() + '-symbols')
    os.makedirs(symbol_temp_dir)

    executables = ['ffmpeg', 'ffprobe']
    base_artifact_name = '-'.join(executables) + '-shared-' + getPlatformMachineVersion()

    # create a log file for the build-ffmpeg command for build archival purposes
    log_file_name = base_artifact_name + '-log.txt'
    log_file_path = os.path.join(output_dir, log_file_name)
    globals()['log_file'] = open(log_file_path, 'w')

    log('Begin build-ffmpeg-descript.py')
    log('=======================')

    # Run the script
    #buildFFmpeg(base_dir, log_file)
    
    # Generate dSYM files for each built library
    log('\nGenerating Symbols')
    log('=======================')
    copyOrGenerateSymbolFiles(packages_dir, symbol_temp_dir, log_file)

    # Generate dSYM files for each executable
    # and copy their dependencies
    for executable in executables:
        log('\nCopying & Linking ' + executable)
        log('=======================')
        executable_path = os.path.join(workspace_bin_dir, executable)
        copyOrGenerateSymbolFile(executable_path, symbol_temp_dir, log_file)
        copyLibraryAndDependencies(executable_path, temp_dir, log_file, executable_path)

        # check that the copied file is runnable
        log('\nChecking ' + executable)
        log('=======================')
        args = [os.path.join(temp_dir, executable), '-version']
        log(' '.join(args))
        output = subprocess.check_output(args)
        log(output.decode('utf-8'))

    symbol_file_name = base_artifact_name + '-symbols'
    shutil.make_archive(os.path.join(output_dir, symbol_file_name), 'zip', symbol_temp_dir)
    shutil.rmtree(symbol_temp_dir)

    # Copy Includes
    shutil.copytree(
      os.path.join(workspace_dir, 'include'),
      os.path.join(temp_dir, 'include'))

    log('\nLibrary Info')
    log('=======================')

    for lib in sorted(missing_libs):
      log('[WARNING] missing ' + lib)

    for lib in sorted(skipped_libs):
      log('[NOTE] skipped ' + lib)

    for lib in sorted(copied_libs):
      log('Copied ' + lib)

    log('\nArchiving third-party source')
    log('=======================')

    # bundle up the third-party source
    # grab each .tar.* and any downloaded patches from the packages folder
    packages_zip_name = base_artifact_name + '-packages.zip'
    with zipfile.ZipFile(os.path.join(output_dir, packages_zip_name), 'w', zipfile.ZIP_DEFLATED) as myzip:
        types = ['*.tar.*', '*.patch', '*.diff']
        for file_type in types:
            archives = pathlib.Path(packages_dir + '/').glob(file_type)
            for archive in sorted(archives, key=lambda s: str(s).lower()):
                log(os.path.join('packages', archive.name))
                myzip.write(str(archive.absolute()), archive.name)

    log('\nArchiving libraries')
    log('=======================')

    # bundle up the build artifacts
    os.chdir(temp_dir)
    shared_zip_name = base_artifact_name + '.tar.gz'
    dest_file = os.path.join(output_dir, shared_zip_name)
    args = ['/usr/bin/tar', 'cvzf', os.path.join('..', shared_zip_name), '.']
    log(' '.join(args))
    subprocess.check_output(args)

    shutil.rmtree(temp_dir)
    
    log('\nEnd of build-ffmpeg-descript.py')
    log('=======================')
    log_file.close()

    # zip up log file
    with zipfile.ZipFile(os.path.splitext(log_file_path)[0] + '.zip', 'w', zipfile.ZIP_DEFLATED) as myzip:
        myzip.write(log_file_path, os.path.basename(log_file_path))
    os.remove(log_file_path)

    generateChecksum(output_dir)

#
#   entry
#
if __name__ == '__main__':
    main()
