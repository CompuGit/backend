```
git remote add backendrepo git@github.com:CompuGit/backend.git
```
```
git subtree add --prefix=backend backendrepo databases --squash
```
```
git fetch backendrepo
```
```
git subtree pull --prefix=backend backendrepo databases --squash
```
```
git add backend/
```
```
git commit -m "Custom updates to backend subtree"
```
```
git subtree push --prefix=backend backendrepo databases
```