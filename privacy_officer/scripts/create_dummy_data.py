import pandas as pd

def create_dummy_data():
    """Generates a CSV file with 10 rows of dummy student feedback in Dutch and English."""
    
    data = {
        'student_id': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        'feedback_text': [
            "De docent Jan Janssen in Eindhoven gaf geweldige lessen, maar het lokaal was vaak koud.",
            "I really enjoyed the specific workshop given by Sarah Smith at the Amsterdam campus.",
            "Het project met meneer De Vries op locatie Rotterdam was erg interessant en leerzaam.",
            "My supervisor Michael Johnson was very helpful during my internship in Utrecht.",
            "De faciliteiten in het gebouw in Den Haag kunnen veel beter, vooral in de kantine van mevrouw Bakker.",
            "I struggled with the final assignment from Dr. Williams. The library in Groningen was also too noisy.",
            "Geweldige begeleiding gehad van docent Pietersen tijdens mijn afstudeerstage in Tilburg.",
            "The administration office in Maastricht, specifically Peter Jones, took way too long to respond to emails.",
            "Mijn mentor Anna de Boer heeft me enorm geholpen toen ik vastliep op de locatie Breda.",
            "The new course taught by Prof. Davis at the campus in Zwolle was quite difficult but rewarding."
        ]
    }
    
    df = pd.DataFrame(data)
    
    output_filename = 'student_feedback.csv'
    df.to_csv(output_filename, index=False)
    print(f"Dummy data generated successfully and saved to {output_filename}")

if __name__ == "__main__":
    create_dummy_data()
