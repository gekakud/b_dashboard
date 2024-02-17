import streamlit_authenticator as stauth

hashed_passwords = stauth.Hasher(['admin', 'def']).generate()
print(hashed_passwords)