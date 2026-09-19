APK Store persistence fix
1) Keep Railway Volume mounted at /data.
2) Replace server.py only.
3) Deploy.
4) APK metadata is now stored at /data/tl_platform/apk_store.json.
5) Existing users/messages remain in /data/tl_platform/data_store.json.
Important: if the previous app card metadata was already lost before this fix, upload that app one final time after deploying this fix. Future deploys will keep it.
