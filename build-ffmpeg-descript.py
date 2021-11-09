#!/usr/bin/env python3

'''
This file is created by Descript to document and augment
the FFmpeg building process, for use in Descript's environment.

(1) Call build-ffmpeg with the build command
(2) Copy or generate dSYM symbol files to the output folder
'''

import glob
import os
import pathlib
import platform
import re
import shutil
import subprocess


cwd = os.path.dirname(os.path.realpath(__file__))
packages_dir = os.path.join(cwd, 'packages')
workspace_dir = os.path.join(cwd, 'workspace')
workspace_bin_dir = os.path.join(workspace_dir, 'bin')
workspace_lib_dir = os.path.join(workspace_dir, 'lib')

skipped_libs = set()
copied_libs = set()
missing_libs = set()
names_without_version = set()

#
#   builds FFmpeg and logs output to build-ffmpeg.log.txt
#
def buildFFmpeg(script_dir, workspace_dir):
    # create a log file for the build-ffmpeg command for build archival purposes
    build_ffmpeg_log_filename = os.path.join(workspace_dir, 'build-ffmpeg.log.txt')
    os.makedirs(os.path.dirname(build_ffmpeg_log_filename), exist_ok=True)
    build_ffmpeg_log_file = open('./workspace/build-ffmpeg.log.txt', 'w')

    # set environment variables
    env = os.environ
    env['SKIPINSTALL'] = 'yes'  # append 'SKIPINSTALL=yes' to skip prompt for installing FFmpeg to /usr/local/bin/etc
    env['VERBOSE'] = 'yes'
    
    # call main build script
    build_ffmpeg_path = os.path.join(script_dir, 'build-ffmpeg')
    subprocess.call([build_ffmpeg_path, '-b', '--full-shared'], env=env, stdout=build_ffmpeg_log_file)

    # close log file
    build_ffmpeg_log_file.close()

#
#   Copies symbol file to the workspace destination
#   skips symlinks to avoid duplication
#   Copies entire dSYM packages for dylib files already within .dSYM packages
#
def copyOrGenerateSymbolFile(file, dest):
    fileref = pathlib.Path(file)
    if not fileref.is_symlink():
        symbolFileName = fileref.name + '.dSYM'
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
            subprocess.call(['/usr/bin/dsymutil', str(fileref), '-o', destPath])

#
#   Copies symbol files to the workspace destination
#   skips symlinks to avoid duplication
#   Copies entire dSYM packages for dylib files already within .dSYM packages
#
def copyOrGenerateSymbolFiles(source, dest):
    for fileref in pathlib.Path(source + '/').glob('**/*.dylib'):
        copyOrGenerateSymbolFile(str(fileref), dest)

'''
const { resolve, basename } = require('path');
const { mkdirSync, readlinkSync, readdirSync } = require('fs');
const { execSync } = require('child_process');

function logAndExec(cmd) {
  console.log(`EXEC ${cmd}`);
  execSync(cmd);
}

const baseIncludesDir = resolve(__dirname, 'workspace/include');
const baseBinDir = resolve(__dirname, 'workspace/bin');
const baseLibDir = resolve(__dirname, 'workspace/lib');
const destDir = resolve(__dirname, 'workspace/mac');

try {
  logAndExec(`rm -r -f ${destDir}`);
} catch (err) {
  //
}
logAndExec(`mkdir -p ${destDir}`);

const skippedLibs = new Set();
const copiedLibs = new Set();
const missingLibs = new Set();
const namesWithoutVersion = new Set();

function copyDylibs(binaryName, base = baseBinDir) {
  const origPath = resolve(base, binaryName);
  const binaryPath = resolve(destDir, binaryName);

  logAndExec(`cp -a ${origPath} ${binaryPath}`);

  const lines = execSync(`otool -L ${binaryPath}`).toString('utf8').split('\n');
  const libsToRewrite = [];
  for (const line of lines) {
    const match = /[^\s:]+/.exec(line);
    if (!match) {
      continue;
    }
    const [path] = match;
    if (path.startsWith('/usr/local')) {
      missingLibs.add(path);
    } else if (path.startsWith('/Users')) {
      const filename = basename(path);
      const newFilename = resolve(destDir, filename);
      if (!copiedLibs.has(path)) {
        copiedLibs.add(path);
        copiedLibs.add(newFilename);
        if (path !== newFilename) {
          // copy sym-linked libraries as well
          let nameWithoutVersion = filename.split('.')[0];
          // libSDL2 weirdly has hypthen after then name (i.e., libSDL2-2.0.0.dylib)
          if (filename.includes('libSDL2')) {
            nameWithoutVersion = 'libSDL2';
          }
          namesWithoutVersion.add(nameWithoutVersion);
          const nameWithoutVersionLib = `${nameWithoutVersion}.dylib`;
          logAndExec(`cp -a ${resolve(baseLibDir, nameWithoutVersion)}*.dylib ${destDir}/.`);

          copyDylibs(filename, baseLibDir);
        }
      }
      libsToRewrite.push({path, filename});
    } else {
      skippedLibs.add(path);
    }
  }

  // find the non-sym-linked version of this library
  let actualBinaryPath = binaryPath;
  try {
    const actualBinaryName = readlinkSync(binaryPath);
    actualBinaryPath = resolve(destDir, actualBinaryName);
  } catch (err) {
    //
  }

  if (libsToRewrite.length > 0) {
    logAndExec(`install_name_tool -id @loader_path/${binaryName} ${libsToRewrite.map(({path, filename}) => `-change ${path} @loader_path/${filename}`).join(' ')} ${actualBinaryPath}`);
  }
}

copyDylibs('ffmpeg');
copyDylibs('ffprobe');

console.log('Copying includes');
logAndExec(`cp -r ${baseIncludesDir} ${destDir}/.`);

for (const lib of Array.from(skippedLibs).sort()) {
  console.log(`[NOTE] skipped ${lib}`);
}
for (const lib of Array.from(copiedLibs).sort()) {
  if (!lib.startsWith(destDir)) {
    console.log(`Copied ${lib}`);
  }
}
for (const lib of Array.from(missingLibs).sort()) {
  console.log(`[WARNING] missing ${lib}`);
}
'''

#
#
#
def copyLibraryAndSymbolPackage(src_file, dest_folder, overwrite):
    dest_file = os.path.join(dest_folder, os.path.basename(src_file))
    
    # copy file
    if overwrite and os.path.exists(dest_file):
        os.remove(dest_file)
    shutil.copy2(src_file, dest_file)

    # copy symbol file
    src_symbol_package = src_file + '.dSYM'
    if os.path.exists(src_symbol_package):
        dest_symbol_package = os.path.join(dest_folder, os.path.basename(src_symbol_package))
        if overwrite and os.path.exists(dest_symbol_package):
          shutil.rmtree(dest_symbol_package)
        if not os.path.exists(dest_symbol_package):
          shutil.copytree(src_symbol_package, dest_symbol_package)


#
# Recursive function to copy a library and its (non-system) dependencies
# also fixes loader paths for each library
#
def copyLibraryAndDependencies(src_file, dest_folder):
    
    dest_file = os.path.join(dest_folder, os.path.basename(src_file))

    # copy file
    copyLibraryAndSymbolPackage(src_file, dest_folder, True)

    # recursively copy dependencies
    otool_proc = subprocess.Popen(['/usr/bin/otool', '-L', src_file], stdout=subprocess.PIPE)
    loader_paths_to_rewrite = []
    for line in otool_proc.stdout:
        ln = line.decode('utf-8').strip()
        match = re.match('[^\s:]+', ln)
        if not match:
            continue
        src_dependency_file = match[0]
        if src_dependency_file.startswith('/usr/local'):
            missing_libs.add(src_dependency_file)
        elif src_dependency_file.startswith(workspace_dir):
            dependency_name = os.path.basename(src_dependency_file)
            dest_dependency_path = os.path.join(dest_folder, dependency_name)
            if not src_dependency_file in copied_libs:
                copied_libs.add(src_dependency_file)
                copied_libs.add(dest_dependency_path)
                if src_dependency_file != dest_dependency_path:
                    # copy sym-linked libraries as well
                    dependency_name_without_version = dependency_name.split('.')[0]
                    # libSDL2 weirdly has hypthen after then name (i.e., libSDL2-2.0.0.dylib)
                    if 'libSDL2' in dependency_name:
                        dependency_name_without_version = 'libSDL2'
                    names_without_version.add(dependency_name_without_version)
                    
                    unversioned_dependency_base_name = os.path.join(workspace_lib_dir, dependency_name_without_version)

                    # Copy each version variant file
                    for variant_file in glob.glob(unversioned_dependency_base_name + r'*.dylib'):
                        copyLibraryAndSymbolPackage(variant_file, dest_folder, False)

                    # RECURSIVELY copy dependencies
                    if (os.path.exists(unversioned_dependency_base_name + '.dylib')):
                        copyLibraryAndDependencies(unversioned_dependency_base_name + '.dylib', dest_folder)
            
            loader_paths_to_rewrite.append({'old_path': src_dependency_file, 'new_path': dest_dependency_path})
        else:
            skipped_libs.add(src_dependency_file)

    # find the non-sym-linked version of this library
    actual_binary_path = os.path.realpath(dest_file)

    if len(loader_paths_to_rewrite) > 0:
        for lib in loader_paths_to_rewrite:
            print(' '.join(['/usr/bin/install_name_tool', '-id', '@loader_path/' + dest_file, '-change', lib['old_path'], '@loader_path/' + os.path.basename(lib['new_path']), actual_binary_path]))
            install_name_tool_proc = subprocess.call(['/usr/bin/install_name_tool', '-id', '@loader_path/' + dest_file, '-change', lib['old_path'], '@loader_path/' + os.path.basename(lib['new_path']), actual_binary_path])

#
#
#
def main():
    output_dir = os.path.join(workspace_dir, 'mac', platform.machine())
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    #buildFFmpeg(cwd, workspace_dir)
    
    # Generate dSYM files for each built library
    #copyOrGenerateSymbolFiles(packages_dir, workspace_lib_dir)

    # Generate dSYM files for each executable
    executables = ['ffmpeg', 'ffprobe']
    for executable in executables:
        executable_path = os.path.join(workspace_bin_dir, executable)
        copyOrGenerateSymbolFile(executable_path, workspace_bin_dir)
        copyLibraryAndDependencies(executable_path, output_dir)

#
#   entry
#
if __name__ == '__main__':
    main()
