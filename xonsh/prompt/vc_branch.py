# -*- coding: utf-8 -*-
"""Prompt formatter for simple version control branchs"""

import os
import sys
import time
import builtins
import warnings
import subprocess

import xonsh.platform as xp


def get_git_branch():
    """Attempts to find the current git branch.  If no branch is found, then
    an empty string is returned. If a timeout occured, the timeout exception
    (subprocess.TimeoutExpired) is returned.
    """
    branch = None
    env = builtins.__xonsh_env__
    cwd = env['PWD']
    denv = env.detype()
    vcbt = env['VC_BRANCH_TIMEOUT']
    if not xp.ON_WINDOWS:
        prompt_scripts = ['/usr/lib/git-core/git-sh-prompt',
                          '/usr/local/etc/bash_completion.d/git-prompt.sh']
        for script in prompt_scripts:
            # note that this is about 10x faster than bash -i "__git_ps1"
            inp = 'source {}; __git_ps1 "${{1:-%s}}"'.format(script)
            try:
                branch = subprocess.check_output(['bash'], cwd=cwd, input=inp,
                                                 stderr=subprocess.PIPE, timeout=vcbt, env=denv,
                                                 universal_newlines=True)
                break
            except subprocess.TimeoutExpired as e:
                branch = e
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
    # fall back to using the git binary if the above failed
    if branch is None:
        cmd = ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
        try:
            s = subprocess.check_output(cmd, cwd=cwd, timeout=vcbt, env=denv,
                                        stderr=subprocess.PIPE, universal_newlines=True)
            if xp.ON_WINDOWS and len(s) == 0:
                # Workaround for a bug in ConEMU/cmder, retry without redirection
                s = subprocess.check_output(cmd, cwd=cwd, timeout=vcbt,
                                            env=denv, universal_newlines=True)
            branch = s.strip()
        except subprocess.TimeoutExpired as e:
            branch = e
        except (subprocess.CalledProcessError, FileNotFoundError):
            branch = None
    return branch


def _get_parent_dir_for(path, dir_name, timeout):
    # walk up the directory tree to see if we are inside an hg repo
    # the timeout makes sure that we don't thrash the file system
    previous_path = ''
    t0 = time.time()
    while path != previous_path and ((time.time() - t0) < timeout):
        if os.path.isdir(os.path.join(path, dir_name)):
            return path
        previous_path = path
        path, _ = os.path.split(path)
    return (path == previous_path)


def get_hg_branch(cwd=None, root=None):
    env = builtins.__xonsh_env__
    cwd = env['PWD']
    root = _get_parent_dir_for(cwd, '.hg', env['VC_BRANCH_TIMEOUT'])
    if not isinstance(root, str):
        # Bail if we are not in a repo or we timed out
        if root:
            return None
        else:
            return subprocess.TimeoutExpired(['hg'], env['VC_BRANCH_TIMEOUT'])
    # get branch name
    branch_path = os.path.sep.join([root, '.hg', 'branch'])
    if os.path.exists(branch_path):
        with open(branch_path, 'r') as branch_file:
            branch = branch_file.read()
    else:
        branch = 'default'
    # add bookmark, if we can
    bookmark_path = os.path.sep.join([root, '.hg', 'bookmarks.current'])
    if os.path.exists(bookmark_path):
        with open(bookmark_path, 'r') as bookmark_file:
            active_bookmark = bookmark_file.read()
        branch = "{0}, {1}".format(*(b.strip(os.linesep) for b in
                                     (branch, active_bookmark)))
    else:
        branch = branch.strip(os.linesep)
    return branch


_FIRST_BRANCH_TIMEOUT = True


def _first_branch_timeout_message():
    global _FIRST_BRANCH_TIMEOUT
    sbtm = builtins.__xonsh_env__['SUPPRESS_BRANCH_TIMEOUT_MESSAGE']
    if not _FIRST_BRANCH_TIMEOUT or sbtm:
        return
    _FIRST_BRANCH_TIMEOUT = False
    print('xonsh: branch timeout: computing the branch name, color, or both '
          'timed out while formatting the prompt. You may avoid this by '
          'increaing the value of $VC_BRANCH_TIMEOUT or by removing branch '
          'fields, like {curr_branch}, from your $PROMPT. See the FAQ '
          'for more details. This message will be suppressed for the remainder '
          'of this session. To suppress this message permanently, set '
          '$SUPPRESS_BRANCH_TIMEOUT_MESSAGE = True in your xonshrc file.',
          file=sys.stderr)


def current_branch(pad=NotImplemented):
    """Gets the branch for a current working directory. Returns an empty string
    if the cwd is not a repository.  This currently only works for git and hg
    and should be extended in the future.  If a timeout occurred, the string
    '<branch-timeout>' is returned.
    """
    if pad is not NotImplemented:
        warnings.warn("The pad argument of current_branch has no effect now "
                      "and will be removed in the future")
    branch = None
    cmds = builtins.__xonsh_commands_cache__
    if cmds.lazy_locate_binary('git') or cmds.is_empty():
        branch = get_git_branch()
    if (cmds.lazy_locate_binary('hg') or cmds.is_empty()) and not branch:
        branch = get_hg_branch()
    if isinstance(branch, subprocess.TimeoutExpired):
        branch = '<branch-timeout>'
        _first_branch_timeout_message()
    return branch or None


def git_dirty_working_directory(cwd=None, include_untracked=False):
    """Returns whether or not the git directory is dirty. If this could not
    be determined (timeout, file not sound, etc.) then this returns None.
    """
    cmd = ['git', 'status', '--porcelain']
    if include_untracked:
        cmd.append('--untracked-files=normal')
    else:
        cmd.append('--untracked-files=no')
    env = builtins.__xonsh_env__
    cwd = env['PWD']
    denv = env.detype()
    vcbt = env['VC_BRANCH_TIMEOUT']
    try:
        s = subprocess.check_output(cmd, stderr=subprocess.PIPE, cwd=cwd,
                                    timeout=vcbt, universal_newlines=True,
                                    env=denv)
        if xp.ON_WINDOWS and len(s) == 0:
            # Workaround for a bug in ConEMU/cmder, retry without redirection
            s = subprocess.check_output(cmd, cwd=cwd, timeout=vcbt,
                                        env=denv, universal_newlines=True)
        return bool(s)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        return None


def hg_dirty_working_directory():
    """Computes whether or not the mercurial working directory is dirty or not.
    If this cannot be deterimined, None is returned.
    """
    env = builtins.__xonsh_env__
    cwd = env['PWD']
    denv = env.detype()
    vcbt = env['VC_BRANCH_TIMEOUT']
    # Override user configurations settings and aliases
    denv['HGRCPATH'] = ''
    try:
        s = subprocess.check_output(['hg', 'identify', '--id'],
                                    stderr=subprocess.PIPE, cwd=cwd, timeout=vcbt,
                                    universal_newlines=True, env=denv)
        return s.strip(os.linesep).endswith('+')
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        return None


def dirty_working_directory(cwd=None):
    """Returns a boolean as to whether there are uncommitted files in version
    control repository we are inside. If this cannot be determined, returns
    None. Currently supports git and hg.
    """
    dwd = None
    cmds = builtins.__xonsh_commands_cache__
    if cmds.lazy_locate_binary('git') or cmds.is_empty():
        dwd = git_dirty_working_directory()
    if (cmds.lazy_locate_binary('hg') or cmds.is_empty()) and (dwd is None):
        dwd = hg_dirty_working_directory()
    return dwd


def branch_color():
    """Return red if the current branch is dirty, yellow if the dirtiness can
    not be determined, and green if it clean. These are bold, intense colors
    for the foreground.
    """
    dwd = dirty_working_directory()
    if dwd is None:
        color = '{BOLD_INTENSE_YELLOW}'
    elif dwd:
        color = '{BOLD_INTENSE_RED}'
    else:
        color = '{BOLD_INTENSE_GREEN}'
    return color


def branch_bg_color():
    """Return red if the current branch is dirty, yellow if the dirtiness can
    not be determined, and green if it clean. These are bacground colors.
    """
    dwd = dirty_working_directory()
    if dwd is None:
        color = '{BACKGROUND_YELLOW}'
    elif dwd:
        color = '{BACKGROUND_RED}'
    else:
        color = '{BACKGROUND_GREEN}'
    return color
