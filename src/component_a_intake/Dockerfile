# Component A - Payment Intake API (Lambda container image, DEC-2).
FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./

# Handler = app.py :: handler
CMD ["app.handler"]
