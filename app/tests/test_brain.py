from ai_brain import JarvisBrain


brain = JarvisBrain()

print("\nTesting OpenAI brain...\n")

response = brain.ask("What time is it? Reply like Jarvis in one short sentence.")

print("JARVIS RESPONSE:")
print(response)