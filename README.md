# Name-Off
This is a simple program to assist with generating names for projects, bands, monsters etc, by throwing together components specified in a file.

It works by running a simulated contest. It begins by generating a set of candidates, then repeatedly prompts the user to compare two candidates to come up with the user's preference. Along the way it tries to mutate existing candidates, sometimes arbitrarily replacing a poor option.

It also learns which components and combinations of components seem to be desirable and uses that to guide future mutations.

## Getting started

1. Clone the repo into a directory called 'name-off' (name is not important, but assumed in these examples).
```
$ git clone <url> name-off
```
2. Make a new sibling directory for your naming contest and change to it.
```
$ mkdir my-naming-contest
$ cd my-naming-contest
```
3. Repeatedly run the update_contest.py script - the first time it runs it will create a bunch of files.
```
$ while true; do python3 ../name-off/update_contest.py; done
```
4. You will be presented with a series of choices on the command line.
5. To pause the contest, press Ctrl-C. You can resume by re-entering step 3.
6. You can see the current ranked candidates in the file 'ranked-candidates'.